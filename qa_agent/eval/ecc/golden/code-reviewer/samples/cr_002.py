"""CSV product importer - massive function mixing parsing, validation, and DB insertion."""
import csv
import io
import re
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation


def import_products_from_csv(csv_content: str, db_path: str, vendor_id: int) -> dict:
    """Import products from CSV string into the database."""
    reader = csv.DictReader(io.StringIO(csv_content))
    required_columns = {"sku", "name", "price", "category", "quantity"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        missing = required_columns - set(reader.fieldnames or [])
        return {"success": False, "error": f"Missing columns: {missing}"}

    imported = []
    skipped = []
    row_number = 1

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for row in reader:
        row_number += 1
        row_errors = []
        sku = row.get("sku", "").strip().upper()
        name = row.get("name", "").strip()
        price_str = row.get("price", "").strip()
        category = row.get("category", "").strip().lower()
        quantity_str = row.get("quantity", "").strip()
        description = row.get("description", "").strip()
        weight_str = row.get("weight", "").strip()
        tags = row.get("tags", "").strip()

        if not sku:
            row_errors.append("SKU is required")
        elif not re.match(r"^[A-Z0-9]{3,20}$", sku):
            row_errors.append("SKU must be 3-20 alphanumeric characters")
        if not name:
            row_errors.append("Name is required")
        elif len(name) > 200:
            row_errors.append("Name must be 200 characters or fewer")
        try:
            price = Decimal(price_str)
            if price <= 0:
                row_errors.append("Price must be positive")
            if price > Decimal("99999.99"):
                row_errors.append("Price exceeds maximum allowed")
        except (InvalidOperation, ValueError):
            row_errors.append("Price must be a valid decimal number")
            price = Decimal("0")
        valid_categories = [
            "electronics", "clothing", "home", "outdoor",
            "automotive", "sporting", "toys", "grocery",
        ]
        if category not in valid_categories:
            row_errors.append(f"Invalid category: {category}")
        try:
            quantity = int(quantity_str)
            if quantity < 0:
                row_errors.append("Quantity cannot be negative")
        except ValueError:
            row_errors.append("Quantity must be an integer")
            quantity = 0
        weight = None
        if weight_str:
            try:
                weight = float(weight_str)
                if weight <= 0:
                    row_errors.append("Weight must be positive")
            except ValueError:
                row_errors.append("Weight must be a number")
        tag_list = []
        if tags:
            tag_list = [t.strip().lower() for t in tags.split(",")]
            tag_list = [t for t in tag_list if t]
            if len(tag_list) > 10:
                row_errors.append("Maximum 10 tags allowed")
            for tag in tag_list:
                if len(tag) > 30:
                    row_errors.append(f"Tag '{tag}' exceeds 30 characters")

        if row_errors:
            skipped.append({"row": row_number, "sku": sku, "errors": row_errors})
            continue

        cursor.execute("SELECT id FROM products WHERE sku = ?", (sku,))
        existing = cursor.fetchone()
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        now = datetime.now().isoformat()

        if existing:
            cursor.execute(
                "UPDATE products SET name=?, price=?, category=?, quantity=?, "
                "description=?, weight=?, tags=?, updated_at=? WHERE sku=?",
                (name, str(price), category, quantity, description,
                 weight, ",".join(tag_list), now, sku),
            )
            imported.append({"sku": sku, "action": "updated", "row": row_number})
        else:
            cursor.execute(
                "INSERT INTO products (sku, name, slug, price, category, quantity, "
                "description, weight, tags, vendor_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sku, name, slug, str(price), category, quantity,
                 description, weight, ",".join(tag_list), vendor_id, now, now),
            )
            imported.append({"sku": sku, "action": "created", "row": row_number})

    conn.commit()
    conn.close()

    return {
        "success": True,
        "total_rows": row_number - 1,
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "imported": imported,
        "skipped": skipped,
        "completed_at": datetime.now().isoformat(),
    }
