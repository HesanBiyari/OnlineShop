from __future__ import annotations
import csv,io
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_GET,require_POST
from .advanced_models import Coupon,Notification,Review,Referral,Wishlist
from .advanced_services import ensure_loyalty,ensure_referral,record_recent_view,reserve_coupon
from .models import DigitalCode,Product,ProductVariant,Order

@login_required
@require_POST
def wishlist_toggle(request,product_id):
    p=get_object_or_404(Product,pk=product_id); x,created=Wishlist.objects.get_or_create(user=request.user,product=p)
    if not created:x.delete();messages.success(request,'از علاقه‌مندی‌ها حذف شد.')
    else:messages.success(request,'به علاقه‌مندی‌ها اضافه شد.')
    next_url = request.POST.get("next", "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("product_detail", pk=p.pk)

@login_required
def wishlist(request):
    return render(request,'wishlist.html',{'products':Product.objects.filter(wishlists__user=request.user).select_related('category').prefetch_related('images','variants')})

@login_required
@require_POST
def review_submit(request,product_id):
    p=get_object_or_404(Product,pk=product_id)
    try:r=max(1,min(5,int(request.POST.get('rating','5'))))
    except ValueError:r=5
    Review.objects.update_or_create(user=request.user,product=p,defaults={'rating':r,'title':request.POST.get('title','')[:120],'body':request.POST.get('body','')[:2000],'is_approved':False})
    messages.success(request,'نظر ثبت شد و پس از بررسی نمایش داده می‌شود.');return redirect('product_detail',pk=p.pk)

@login_required
@require_POST
def coupon_apply(request):
    cart=request.session.get('cart',{});total=0
    for key,q in cart.items() if isinstance(cart,dict) else []:
        try:pid,vid=map(int,str(key).split(':',1));q=max(0,int(q))
        except (ValueError,TypeError):continue
        p=Product.objects.filter(pk=pid).select_related('discount').first()
        if not p:continue
        v=ProductVariant.objects.filter(pk=vid,product=p,is_active=True).first() if vid else None
        if vid and not v:continue
        total+=(v.final_price if v else p.final_price)*q
    c,d,e=reserve_coupon(request.POST.get('code'),request.user,total)
    if e:messages.error(request,e)
    else:request.session.update(coupon_code=c.code,coupon_discount=d);request.session.modified=True;messages.success(request,f'تخفیف {d:,} تومان اعمال شد.')
    return redirect('checkout')

@login_required
@require_POST
def coupon_remove(request):
    request.session.pop('coupon_code',None);request.session.pop('coupon_discount',None);request.session.modified=True;return redirect('checkout')

@login_required
def notifications(request):
    rows=Notification.objects.filter(user=request.user);Notification.objects.filter(user=request.user,is_read=False).update(is_read=True)
    return render(request,'notifications.html',{'notifications':rows})

@login_required
def referral(request):return render(request,'referral.html',{'referral':ensure_referral(request.user)})

@login_required
@require_POST
def referral_apply(request):
    r=Referral.objects.filter(code=request.POST.get('code','').strip().upper()).select_related('user').first()
    mine=ensure_referral(request.user)
    if not r or r.user_id==request.user.id or mine.referred_by_id:messages.error(request,'کد معرفی معتبر نیست یا قبلاً ثبت شده است.')
    else:mine.referred_by=r.user;mine.save(update_fields=['referred_by']);messages.success(request,'کد معرفی ثبت شد.')
    return redirect('referral')

@login_required
def loyalty(request):return render(request,'loyalty.html',{'loyalty':ensure_loyalty(request.user)})

@staff_member_required
@require_GET
def codes_export(request):
    response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="giftweb-digital-codes.csv"';response.write('\ufeff')
    w=csv.writer(response);w.writerow(['code','pin','product_id','variant_id','is_used','order_item_id','used_at'])
    for c in DigitalCode.objects.order_by('id'):w.writerow([c.code,c.pin,c.product_id,c.variant_id or '',int(c.is_used),c.order_item_id or '',c.used_at.isoformat() if c.used_at else ''])
    return response

@staff_member_required
def codes_import(request):
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "CSV انتخاب نشده است.")
            return redirect("codes_import")
        try:
            decoded = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "فایل CSV باید UTF-8 باشد.")
            return redirect("codes_import")

        created = duplicates = invalid = 0
        with transaction.atomic():
            for row in csv.DictReader(io.StringIO(decoded)):
                code = (row.get("code") or "").strip()
                if not code:
                    invalid += 1
                    continue
                if DigitalCode.objects.filter(code=code).exists():
                    duplicates += 1
                    continue
                try:
                    product_id = int(row["product_id"])
                    variant_id = int(row["variant_id"]) if row.get("variant_id") else None
                    obj = DigitalCode(
                        code=code,
                        pin=(row.get("pin") or "").strip(),
                        product_id=product_id,
                        variant_id=variant_id,
                    )
                    obj.full_clean()
                    obj.save()
                    created += 1
                except (KeyError, TypeError, ValueError, ValidationError):
                    invalid += 1

        messages.success(
            request,
            f"{created} کد وارد شد؛ {duplicates} تکراری و {invalid} ردیف نامعتبر نادیده گرفته شد.",
        )
        return redirect("codes_import")
    return render(request, "admin_tools/codes_import.html")

@staff_member_required
def analytics(request):
    total=Order.objects.filter(status__in=('paid','processing','completed')).aggregate(x=Sum('total_amount'))['x'] or 0
    today=Order.objects.filter(status__in=('paid','processing','completed'),created_at__date=timezone.localdate()).aggregate(x=Sum('total_amount'))['x'] or 0
    return render(request,'admin_tools/analytics.html',{'revenue':total,'today':today})
