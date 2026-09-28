
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .advanced_models import Coupon,LoyaltyAccount,LoyaltyTransaction,Notification,Referral,Review,Wishlist
from .advanced_services import award_points,ensure_referral,reserve_coupon
from .models import Category,Order,Product

class AdvancedFeatureTests(TestCase):
 def setUp(self):
  self.user=User.objects.create_user(username='adv1',password='StrongPass123!')
  self.other=User.objects.create_user(username='adv2',password='StrongPass123!')
  c=Category.objects.create(name='Advanced',slug='advanced-test')
  self.product=Product.objects.create(category=c,name='Advanced Product',price=100000,stock=10)
 def test_wishlist_toggle_and_isolation(self):
  self.client.force_login(self.user);self.client.post(reverse('wishlist_toggle',args=[self.product.pk]))
  self.assertTrue(Wishlist.objects.filter(user=self.user,product=self.product).exists())
  self.client.force_login(self.other);self.assertNotContains(self.client.get(reverse('wishlist')),self.product.name)
 def test_review_is_unique(self):
  self.client.force_login(self.user);self.client.post(reverse('review_submit',args=[self.product.pk]),{'rating':'5','body':'great'})
  self.client.post(reverse('review_submit',args=[self.product.pk]),{'rating':'4','body':'updated'})
  self.assertEqual(Review.objects.filter(user=self.user,product=self.product).count(),1)
 def test_coupon(self):
  c=Coupon.objects.create(code='TEST10',kind='percent',value=10)
  selected,discount,error=reserve_coupon('TEST10',self.user,100000)
  self.assertFalse(error);self.assertEqual(selected.pk,c.pk);self.assertEqual(discount,10000)
 def test_loyalty_and_notification(self):
  order=Order.objects.create(user=self.user,full_name='A',email='a@b.com',phone='09121234567',total_amount=250000)
  award_points(self.user,25,'خرید',order)
  self.assertEqual(LoyaltyAccount.objects.get(user=self.user).points,25)
  self.assertTrue(LoyaltyTransaction.objects.filter(order=order).exists())
  Notification.objects.create(user=self.user,title='ok')
  self.assertEqual(Notification.objects.filter(user=self.user).count(),1)
 def test_referral(self):
  r=ensure_referral(self.user);self.assertTrue(r.code.startswith('GW-'));self.assertEqual(Referral.objects.filter(user=self.user).count(),1)
