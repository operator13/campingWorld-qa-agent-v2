"""N+1 query: fetching related data one row at a time in a loop."""
import sqlite3


def get_orders_with_items(db_path: str) -> list[dict]:
    """Fetch all orders and their line items."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, customer_id, total FROM orders")
    orders = cursor.fetchall()

    results = []
    for order in orders:
        order_id = order[0]
        # One query per order -- classic N+1
        cursor.execute(
            "SELECT product_name, quantity, price FROM order_items WHERE order_id = ?",
            (order_id,),
        )
        items = cursor.fetchall()
        results.append({
            "order_id": order_id,
            "customer_id": order[1],
            "total": order[2],
            "items": [{"name": i[0], "qty": i[1], "price": i[2]} for i in items],
        })

    conn.close()
    return results
