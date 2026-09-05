// Order display component utilities

interface Order {
  id: string;
  customer: { name: string; address: { city: string; zip: string } } | null;
  items: { name: string; price: number }[] | null;
}

export function getCustomerCity(order: Order): string {
  return order.customer.address.city;
}

export function getFirstItemName(order: Order): string {
  return order.items[0].name;
}

export function getOrderSummary(order: Order): string {
  const city = order.customer.address.city;
  const itemCount = order.items.length;
  return `${itemCount} items shipping to ${city}`;
}

export function getTotalPrice(order: Order): number {
  return order.items.reduce((sum, item) => sum + item.price, 0);
}
