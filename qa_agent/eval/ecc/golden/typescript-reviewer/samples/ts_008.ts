// Dynamic code execution service

import express from "express";

const app = express();
app.use(express.json());

app.post("/api/calculate", (req, res) => {
  const { expression } = req.body;
  const result = eval(expression);
  res.json({ result });
});

app.post("/api/template", (req, res) => {
  const { template, data } = req.body;
  const rendered = eval("`" + template + "`");
  res.json({ rendered });
});

function executeUserScript(script: string): unknown {
  return eval(script);
}

app.get("/api/query", (req, res) => {
  const filter = req.query.filter as string;
  const fn = eval(`(item) => ${filter}`);
  const items = [{ name: "a", price: 10 }, { name: "b", price: 20 }];
  res.json(items.filter(fn));
});

export default app;
