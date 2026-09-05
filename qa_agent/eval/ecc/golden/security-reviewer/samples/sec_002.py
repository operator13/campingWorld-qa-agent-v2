"""Django view with SQL injection via ORM raw query."""
from django.http import JsonResponse
from django.db import connection


def search_products(request):
    """Search products by name using raw SQL."""
    search_term = request.GET.get("q", "")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, name, price FROM products WHERE name LIKE '%%%s%%'" % search_term
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return JsonResponse({"results": rows})


def product_detail(request, product_id):
    """Get product detail by ID."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, name, price, description FROM products WHERE id = %s",
            [product_id],
        )
        row = cursor.fetchone()
    if not row:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse({"id": row[0], "name": row[1], "price": row[2]})
