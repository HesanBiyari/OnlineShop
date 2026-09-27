from __future__ import annotations
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.forms import modelform_factory
from django import forms
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Category, DigitalCode, Discount, Order, OrderItem, Payment, Product, ProductImage, ProductVariant
from .advanced_models import Coupon, CouponRedemption, LoyaltyAccount, LoyaltyTransaction, Notification, RecentlyViewed, Referral, Review, Wishlist

User = get_user_model()


def staff_required(view):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url='/django-admin/login/',
    )(view)

MODEL_MAP = {
    'products': Product,
    'categories': Category,
    'variants': ProductVariant,
    'images': ProductImage,
    'discounts': Discount,
    'codes': DigitalCode,
    'orders': Order,
    'order-items': OrderItem,
    'payments': Payment,
    'coupons': Coupon,
    'coupon-redemptions': CouponRedemption,
    'reviews': Review,
    'referrals': Referral,
    'loyalty': LoyaltyAccount,
    'loyalty-transactions': LoyaltyTransaction,
    'notifications': Notification,
    'recently-viewed': RecentlyViewed,
    'users': User,
    'groups': Group,
}

MODEL_LABELS = {
    'products':'محصولات', 'categories':'دسته‌بندی‌ها', 'variants':'تنوع‌ها', 'images':'تصاویر',
    'discounts':'تخفیف‌ها', 'codes':'کدهای دیجیتال', 'orders':'سفارش‌ها', 'order-items':'آیتم‌های سفارش',
    'payments':'پرداخت‌ها', 'coupons':'کوپن‌ها', 'coupon-redemptions':'مصرف کوپن', 'reviews':'نظرات',
    'referrals':'معرفی‌ها', 'loyalty':'وفاداری', 'loyalty-transactions':'تراکنش امتیاز',
    'notifications':'اعلان‌ها', 'recently-viewed':'بازدیدهای اخیر', 'users':'کاربران', 'groups':'دسترسی‌ها',
}

ADMIN_NAV = [
    ('dashboard','داشبورد','📊'),
    ('products','محصولات','🛍️'),
    ('categories','دسته‌بندی‌ها','🗂️'),
    ('variants','تنوع‌ها','🎛️'),
    ('discounts','تخفیف‌ها','🏷️'),
    ('codes','کدهای دیجیتال','🔐'),
    ('orders','سفارش‌ها','📦'),
    ('payments','پرداخت‌ها','💳'),
    ('coupons','کوپن‌ها','🎟️'),
    ('reviews','نظرات','⭐'),
    ('users','کاربران','👥'),
    ('groups','دسترسی‌ها','🛡️'),
]


def _qs_for_key(key):
    model = MODEL_MAP.get(key)
    if model is None:
        return None
    return model.objects.all()


def _editable_fields(model, key):
    if key == 'users':
        return ['username','first_name','last_name','email','is_active','is_staff','is_superuser']
    if key == 'groups':
        return ['name','permissions']
    fields=[]
    blocked={'created_at','updated_at','used_at','final_price','catalog_price','is_used'}
    for field in model._meta.get_fields():
        if not getattr(field,'editable',False):
            continue
        if getattr(field,'auto_created',False) or getattr(field,'many_to_many',False) or getattr(field,'one_to_many',False):
            continue
        if field.name in blocked:
            continue
        if key == 'products' and field.name == 'slug':
            continue
        if key in {'orders','payments','order-items','coupon-redemptions','loyalty-transactions','recently-viewed'} and field.name in {'user','order','order_item','payment','authority'}:
            continue
        fields.append(field.name)
    return fields


def _model_form(key, instance=None, data=None, files=None):
    model=MODEL_MAP[key]
    Form=modelform_factory(model, fields=_editable_fields(model,key))
    return Form(data=data, files=files, instance=instance)


class ProductImageUploadForm(forms.Form):
    image=forms.ImageField(required=True)

def _validate_product_images(files):
    errors=[]
    for uploaded in files:
        f=ProductImageUploadForm(files={'image': uploaded})
        if not f.is_valid():
            name=getattr(uploaded,'name','تصویر')
            errors.append(f'{name}: ' + '; '.join(str(e) for e in f.errors.get('image',[])))
    return errors

def _save_product_images(product, request):
    uploads=request.FILES.getlist('product_images')
    if not uploads:
        single=request.FILES.get('product_images')
        uploads=[single] if single else []
    if not uploads:
        return []
    errors=_validate_product_images(uploads)
    if errors:
        return errors
    make_main=request.POST.get('make_main_image') == '1'
    alt_text=request.POST.get('image_alt_text','').strip()[:200]
    has_main=ProductImage.objects.filter(product=product,is_main=True).exists()
    with transaction.atomic():
        if make_main:
            ProductImage.objects.filter(product=product,is_main=True).update(is_main=False)
        for index,uploaded in enumerate(uploads):
            ProductImage.objects.create(
                product=product,
                image=uploaded,
                alt_text=alt_text or getattr(uploaded,'name','').rsplit('.',1)[0][:200],
                is_main=(index == 0 and (make_main or not has_main)),
            )
    return []

def dashboard(request):
    today=timezone.localdate()
    paid_statuses=('paid','processing','completed')
    orders_today=Order.objects.filter(created_at__date=today).count()
    sales_today=Order.objects.filter(status__in=paid_statuses, created_at__date=today).aggregate(v=Sum('total_amount'))['v'] or 0
    revenue=Order.objects.filter(status__in=paid_statuses).aggregate(v=Sum('total_amount'))['v'] or 0
    pending=Order.objects.filter(status='pending').count()
    processing=Order.objects.filter(status='processing').count()
    failed_payments=Payment.objects.filter(status='failed').count()
    low_stock=Product.objects.filter(stock__lte=3).count()
    available_codes=DigitalCode.objects.filter(is_used=False).count()
    chart=[]
    for offset in range(6,-1,-1):
        day=today-timedelta(days=offset)
        amount=Order.objects.filter(status__in=paid_statuses,created_at__date=day).aggregate(v=Sum('total_amount'))['v'] or 0
        chart.append({'label':day.strftime('%m/%d'),'value':int(amount)})
    max_value=max([x['value'] for x in chart], default=0) or 1
    for item in chart:
        item['height']=max(8,int(item['value']*100/max_value))
    context={
        'stats': {
            'sales_today':sales_today, 'orders_today':orders_today, 'pending':pending,
            'processing':processing, 'revenue':revenue, 'failed_payments':failed_payments,
            'low_stock':low_stock, 'available_codes':available_codes,
        },
        'chart':chart,
        'recent_orders':Order.objects.select_related('user').order_by('-created_at','-id')[:8],
        'recent_payments':Payment.objects.select_related('order').order_by('-created_at','-id')[:8],
        'attention_orders':Order.objects.select_related('user').filter(status='processing').order_by('-created_at')[:6],
        'low_stock_products':Product.objects.filter(stock__lte=3).order_by('stock','name')[:6],
        'nav':ADMIN_NAV,
        'active':'dashboard',
    }
    return render(request,'admin_panel/dashboard.html',context)

dashboard = staff_required(dashboard)


def model_list(request,key):
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    qs=qs.order_by('-pk')
    query=request.GET.get('q','').strip()
    if query:
        q=Q()
        for field in qs.model._meta.get_fields():
            if not getattr(field,'concrete',False):
                continue
            if field.get_internal_type() in {'CharField','TextField','SlugField','EmailField'}:
                q |= Q(**{f'{field.name}__icontains':query})
        if q:
            qs=qs.filter(q)
    paginator=Paginator(qs,15)
    page=paginator.get_page(request.GET.get('page'))
    fields=[]
    for field in qs.model._meta.get_fields():
        if getattr(field,'concrete',False) and not getattr(field,'auto_created',False) and not getattr(field,'many_to_many',False) and not getattr(field,'one_to_many',False):
            fields.append(field)
        if len(fields)>=6:
            break
    return render(request,'admin_panel/model_list.html',{
        'key':key, 'title':MODEL_LABELS.get(key,key), 'page':page, 'fields':fields,
        'nav':ADMIN_NAV, 'active':key, 'query':query,
    })

model_list = staff_required(model_list)


def model_create(request,key):
    if key not in MODEL_MAP:
        return redirect('admin_dashboard')
    form=_model_form(key)
    image_errors=[]
    if request.method=='POST':
        form=_model_form(key,data=request.POST,files=request.FILES)
        if form.is_valid():
            if key=='products':
                image_errors=_validate_product_images(request.FILES.getlist('product_images'))
            if not image_errors:
                obj=form.save()
                if key=='products':
                    image_errors=_save_product_images(obj,request)
                    if image_errors:
                        obj.delete()
                        return render(request,'admin_panel/model_form.html',{
                            'key':key,'title':'افزودن '+MODEL_LABELS.get(key,key),'form':form,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
                        })
                messages.success(request,'مورد جدید با موفقیت ایجاد شد.')
                return redirect('admin_model_edit',key=key,pk=obj.pk)
    return render(request,'admin_panel/model_form.html',{
        'key':key,'title':'افزودن '+MODEL_LABELS.get(key,key),'form':form,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
    })

model_create = staff_required(model_create)


def model_edit(request,key,pk):
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    obj=get_object_or_404(qs,pk=pk)
    form=_model_form(key,instance=obj)
    image_errors=[]
    if request.method=='POST':
        form=_model_form(key,instance=obj,data=request.POST,files=request.FILES)
        if form.is_valid():
            if key=='products':
                image_errors=_validate_product_images(request.FILES.getlist('product_images'))
            if not image_errors:
                form.save()
                if key=='products':
                    image_errors=_save_product_images(obj,request)
                    if image_errors:
                        messages.error(request,'تصویر اضافه نشد؛ اطلاعات محصول ذخیره شد.')
                        image_errors=[]
                if not image_errors:
                    messages.success(request,'تغییرات با موفقیت ذخیره شد.')
                    return redirect('admin_model_list',key=key)
    return render(request,'admin_panel/model_form.html',{
        'key':key,'title':'ویرایش '+MODEL_LABELS.get(key,key),'form':form,'object':obj,'nav':ADMIN_NAV,'active':key,'image_errors':image_errors,
    })

model_edit = staff_required(model_edit)


def model_delete(request,key,pk):
    qs=_qs_for_key(key)
    if qs is None:
        return redirect('admin_dashboard')
    obj=get_object_or_404(qs,pk=pk)
    if key=='users' and obj.pk==request.user.pk:
        messages.error(request,'حساب مدیر فعلی قابل حذف نیست.')
    else:
        obj.delete()
        messages.success(request,'مورد با موفقیت حذف شد.')
    return redirect('admin_model_list',key=key)

model_delete = staff_required(model_delete)


def logout_view(request):
    logout(request)
    return redirect('/django-admin/login/')

logout_view = staff_required(logout_view)
