// React component with missing useEffect dependency array

import React, { useState, useEffect } from "react";

interface Product {
  id: string;
  name: string;
  price: number;
}

export function ProductList({ categoryId }: { categoryId: string }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`/api/products?category=${categoryId}`)
      .then((res) => res.json())
      .then((data) => setProducts(data));
  });

  useEffect(() => {
    document.title = `${products.length} products found`;
  });

  const filtered = products.filter((p) => p.name.includes(search));

  return (
    <div>
      <input value={search} onChange={(e) => setSearch(e.target.value)} />
      <ul>
        {filtered.map((p) => (
          <li key={p.id}>{p.name} - ${p.price}</li>
        ))}
      </ul>
    </div>
  );
}
