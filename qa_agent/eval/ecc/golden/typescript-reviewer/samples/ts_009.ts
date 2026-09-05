// Express API handlers without input validation

import express from "express";

const router = express.Router();

router.post("/api/users", (req, res) => {
  const { name, email, age } = req.body;
  const user = {
    id: Math.random().toString(36),
    name,
    email,
    age,
    createdAt: new Date().toISOString(),
  };
  res.status(201).json(user);
});

router.put("/api/users/:id", (req, res) => {
  const { role, permissions } = req.body;
  // directly trusting client-supplied role and permissions
  const updated = { id: req.params.id, role, permissions };
  res.json(updated);
});

router.post("/api/orders", (req, res) => {
  const { items, shippingAddress, paymentMethod } = req.body;
  const total = items.reduce(
    (sum: number, item: { price: number; qty: number }) => sum + item.price * item.qty,
    0
  );
  res.json({ orderId: Date.now().toString(), total, shippingAddress });
});

export default router;
