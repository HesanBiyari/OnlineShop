from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from .models import Category, Product

class AdminPanelTests(TestCase):
    def setUp(self):
        self.staff=User.objects.create_user(username='paneladmin',password='StrongPass123!',is_staff=True)
        self.user=User.objects.create_user(username='normaluser',password='StrongPass123!')
        category=Category.objects.create(name='Panel',slug='panel-test')
        self.product=Product.objects.create(category=category,name='Panel Product',price=100000,stock=5)

    def test_dashboard_requires_staff(self):
        self.client.force_login(self.user)
        response=self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code,302)

    def test_staff_dashboard(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'داشبورد فروشگاه')
        self.assertContains(response,'فروش امروز')

    def test_product_crud_panel(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('admin_model_list',args=['products']))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.product.name)
        response=self.client.get(reverse('admin_model_create',args=['products']))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'ذخیره')


    def test_product_image_upload_from_product_form(self):
        self.client.force_login(self.staff)
        out=BytesIO()
        Image.new('RGB',(8,8),(120,120,120)).save(out,format='JPEG')
        out.seek(0)
        image=SimpleUploadedFile('steam-card.jpg',out.read(),content_type='image/jpeg')
        response=self.client.post(reverse('admin_model_edit',args=['products',self.product.pk]),{
            'category':self.product.category_id,
            'name':self.product.name,
            'description':self.product.description,
            'price':self.product.price,
            'stock':self.product.stock,
            'is_bestseller':'',
            'bestseller_priority':self.product.bestseller_priority,
            'image_alt_text':'Steam Gift Card',
            'product_images': image,
        })
        self.assertEqual(response.status_code,302)
        from .models import ProductImage
        img=ProductImage.objects.get(product=self.product)
        self.assertTrue(img.is_main)
        self.assertEqual(img.alt_text,'Steam Gift Card')
        self.assertTrue(img.image.name.endswith('steam-card.jpg'))

    def test_admin_root_redirects_to_giftweb_dashboard(self):
        self.client.force_login(self.staff)
        response=self.client.get('/admin/')
        self.assertEqual(response.status_code,302)
        self.assertTrue(response['Location'].endswith('/dashboard/'))
