# GIFTWEB_FINAL_PACKAGE_V1
from __future__ import annotations
import secrets,string
from django.db import transaction
from django.utils import timezone
from .advanced_models import Coupon,CouponRedemption,LoyaltyAccount,LoyaltyTransaction,Notification,Referral,RecentlyViewed

def referral_code(): return 'GW-'+''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(10))

def ensure_referral(user,referred_by=None):
    obj,created=Referral.objects.get_or_create(user=user,defaults={'code':referral_code(),'referred_by':referred_by})
    if not created and referred_by and not obj.referred_by_id and referred_by.id!=user.id:
        obj.referred_by=referred_by; obj.save(update_fields=['referred_by'])
    return obj

def ensure_loyalty(user): return LoyaltyAccount.objects.get_or_create(user=user)[0]

def notify(user,title,body=''): return Notification.objects.create(user=user,title=title,body=body)

def award_points(user,points,reason,order=None):
    if points<=0:return 0
    with transaction.atomic():
        acc=LoyaltyAccount.objects.select_for_update().get_or_create(user=user)[0]
        acc.points+=points; acc.lifetime_points+=points; acc.save(update_fields=['points','lifetime_points','updated_at'])
        LoyaltyTransaction.objects.create(account=acc,points=points,reason=reason,order=order)
    return points

def finalize_advanced_order(order):
    if not LoyaltyTransaction.objects.filter(order=order,reason='خرید').exists():
        award_points(order.user,order.total_amount//10000,'خرید',order)
        notify(order.user,'پرداخت موفق',f'سفارش #{order.id} با موفقیت تأیید شد.')
    ensure_referral(order.user)
    return True

def reserve_coupon(code,user,amount):
    code=str(code or '').strip().upper()
    if not code:return None,0,'کد تخفیف را وارد کنید.'
    with transaction.atomic():
        c=Coupon.objects.select_for_update().filter(code=code).first()
        if not c or not c.is_valid_now:return None,0,'کد تخفیف معتبر یا فعال نیست.'
        if CouponRedemption.objects.filter(coupon=c,user=user).exists():return None,0,'این کد قبلاً استفاده شده است.'
        d=c.discount_for(amount)
        if not d:return None,0,'شرایط استفاده از این کد برای سفارش برقرار نیست.'
        return c,d,''

def release_coupon_for_order(order):
    r=getattr(order,'coupon_redemption',None)
    if not r:return
    with transaction.atomic():
        c=Coupon.objects.select_for_update().get(pk=r.coupon_id)
        if c.used_count:c.used_count-=1;c.save(update_fields=['used_count'])

def record_recent_view(request,product):
    if not request.session.session_key: request.session.create()
    if request.user.is_authenticated:
        RecentlyViewed.objects.update_or_create(user=request.user,session_key='',product=product,defaults={'viewed_at':timezone.now()})
    else:
        RecentlyViewed.objects.update_or_create(user=None,session_key=request.session.session_key,product=product,defaults={'viewed_at':timezone.now()})
