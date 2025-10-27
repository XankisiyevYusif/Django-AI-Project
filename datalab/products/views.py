import os
import json

from django.db.models import Count, Sum, Avg, ExpressionWrapper,F,DecimalField
from django.db.models.functions import TruncMonth, ExtractQuarter
from django.http import FileResponse
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder

from . import utils
from .forms import UploadForm, DateFilterForm
from .models import Product
import pandas as pd

from django.conf import settings

# Create your views here.

def dashboard(request):
    kpi=Product.objects.aggregate(
        products=Count('id'),
        total_qty=Sum('quantity'),
        avg_price=Avg('price')
    )

    #top categories income
    revenue_expr=ExpressionWrapper(F("price")*F("quantity"),
                                   output_field=DecimalField(max_digits=14,decimal_places=2))

    top_cats=(Product.objects.values("category")
              .annotate(revenue=Sum(revenue_expr),items=Count("id"))
              .order_by("-revenue")[:5])

    return render(request,"products/dashboard.html",{"kpi":kpi,"top_cats":top_cats})

def product_upload(request):
    ctx = {"form": UploadForm()}

    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)

        if form.is_valid():
            files = request.FILES.getlist("file")  # Bütün faylları al
            sheet = form.cleaned_data.get("sheet_name") or None

            updir = os.path.join(settings.MEDIA_ROOT, "uploads")
            os.makedirs(updir, exist_ok=True)

            total_rows = 0

            for up in files:
                fpath = os.path.join(updir, up.name)

                with open(fpath, "wb+") as dest:
                    for ch in up.chunks():
                        dest.write(ch)

                df = utils.read_any(fpath, sheet)
                df = utils.normalize_for_product(df)

                rows = df.to_dict("records")

                for r in rows:
                    Product.objects.update_or_create(
                        sku=r["sku"],
                        defaults=dict(
                            name=r["name"],
                            price=r["price"],
                            quantity=int(r["quantity"]),
                            category=r.get("category") or "",
                            tx_date=r["tx_date"],
                        )
                    )

                total_rows += len(rows)

            ctx["msg"] = f"✓ Uploaded {len(files)} file(s), {total_rows} total rows"
            ctx["form"] = UploadForm()

    return render(request, "products/upload.html", ctx)


def product_list(request):
    form=DateFilterForm(request.GET or None)
    qs=Product.objects.all().order_by("-tx_date","-id")

    if form.is_valid():
        df=form.cleaned_data.get("date_from")
        dt=form.cleaned_data.get("date_to")
        cat=form.cleaned_data.get("category")
        if df:
            qs=qs.filter(tx_date__gte=df)
        if dt:
            qs=qs.filter(tx_date__lte=dt)
        if cat:
            qs=qs.filter(category__icontains=cat)
    return render(request,"products/product_list.html",{"form":form,"qs":qs})

def product_export(request):
    qs=Product.objects.all().order_by("-tx_date","sku")
    data=qs.values('sku','name','category','price','quantity','tx_date')
    df=pd.DataFrame.from_records(data)
    path=utils.df_to_excel_response(df,"products_export.xlsx")
    return FileResponse(open(path,"rb"),as_attachment=True,filename=os.path.basename(path))


def stats_view(request):
    revenue_expr = ExpressionWrapper(F("price") * F("quantity"),
                                     output_field=DecimalField(max_digits=14, decimal_places=2))

    # 1 Monthly income
    monthly_qs = (Product.objects
               .annotate(month=TruncMonth("tx_date"))
               .values("month")
               .annotate(revenue=Sum(revenue_expr), items=Count("id"))
               .order_by("month")
               )

    quarterly_qs = (Product.objects
                 .annotate(q=ExtractQuarter("tx_date"))
                 .values("q")
                 .annotate(revenue=Sum(revenue_expr), avg_price=Avg("price"))
                 .order_by("q"))

    by_cat_qs = (Product.objects
              .values("category")
              .annotate(mean_price=Avg("price"), total_qty=Sum("quantity"))
              .order_by("-total_qty"))

    top_sku_qs = (Product.objects
        .values("sku", "name", "category")
        .annotate(revenue=Sum(revenue_expr), qty=Sum("quantity"))
        .order_by("-revenue")[:10])

    low_stock_qs = Product.objects.filter(quantity__lte=5).order_by("quantity", "name")[:10]

    monthly = list(monthly_qs)
    quarterly = list(quarterly_qs)
    by_cat = list(by_cat_qs)
    top_sku = list(top_sku_qs)
    low_stock = list(low_stock_qs.values("id", "sku", "name", "quantity"))

    ctx = {
        "monthly": monthly,
        "quarterly": quarterly,
        "by_cat": by_cat,
        "top_sku": top_sku,
        "low_stock": low_stock,

        "monthly_json": json.dumps(monthly, cls=DjangoJSONEncoder),
        "quarterly_json": json.dumps(quarterly, cls=DjangoJSONEncoder),
        "by_cat_json": json.dumps(by_cat, cls=DjangoJSONEncoder),
        "top_sku_json": json.dumps(top_sku, cls=DjangoJSONEncoder),
        "low_stock_json": json.dumps(low_stock, cls=DjangoJSONEncoder),
    }

    return render(request, "products/stats.html", ctx)