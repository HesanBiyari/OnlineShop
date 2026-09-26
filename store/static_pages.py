from django.shortcuts import render
def about(request): return render(request, "about.html")
def contact(request): return render(request, "contact.html")
def faq(request): return render(request, "faq.html")
def guide(request): return render(request, "guide.html")
def terms(request): return render(request, "terms.html")
def privacy(request): return render(request, "privacy.html")