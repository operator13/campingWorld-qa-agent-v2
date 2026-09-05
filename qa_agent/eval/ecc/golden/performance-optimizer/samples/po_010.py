"""Batch DB query using IN clause instead of N+1 loop."""
import sqlite3


def get_orders_with_items(db_path: str) -> list[dict]:
    """Fetch all orders and their line items using a single batch query."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, customer_id, total FROM orders")
    orders = cursor.fetchall()

    if not orders:
        conn.close()
        return []

    order_ids = [o[0] for o in orders]
    placeholders = ",".join("?" for _ in order_ids)
    cursor.execute(
        f"SELECT order_id, product_name, quantity, price "
        f"FROM order_items WHERE order_id IN ({placeholders})",
        order_ids,
    )
    all_items = cursor.fetchall()
    conn.close()

    items_by_order: dict[int, list[dict]] = {}
    for item in all_items:
        items_by_order.setdefault(item[0], []).append(
            {"name": item[1], "qty": item[2], "price": item[3]}
        )

    return [
        {
            "order_id": o[0],
            "customer_id": o[1],
            "total": o[2],
            "items": items_by_order.get(o[0], []),
        }
        for o in orders
    ]
