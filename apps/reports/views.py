import json

from django.http import HttpResponse
from django.shortcuts import render

from apps.catalog.sell_views import seller_required
from apps.moderation.views import mod_render, staff_required

from . import services


@seller_required
def seller_stats(request):
    d_from, d_to = services.parse_period(request.GET)
    stats = services.seller_stats(request.user, d_from, d_to)
    chart = {"labels": stats["labels"], "sales": stats["sales"], "revenue": stats["revenue"], "views": stats["views"]}
    return render(
        request,
        "sell/stats.html",
        {"stats": stats, "chart_json": json.dumps(chart), "d_from": d_from, "d_to": d_to, "sell_tab": "stats"},
    )


@staff_required
def admin_reports(request):
    d_from, d_to = services.parse_period(request.GET, default_days=365)
    return mod_render(
        request,
        "moderation/reports.html",
        {"report": services.admin_report(d_from, d_to), "d_from": d_from, "d_to": d_to},
        "reports",
    )


@staff_required
def admin_reports_excel(request):
    d_from, d_to = services.parse_period(request.GET, default_days=365)
    data = services.admin_report_xlsx(d_from, d_to)
    resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="codemarket-report-{d_from:%Y%m%d}-{d_to:%Y%m%d}.xlsx"'
    return resp
