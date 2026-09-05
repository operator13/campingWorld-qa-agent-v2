// React component with correct useEffect dependencies

import React, { useState, useEffect, useCallback, useMemo } from "react";

interface Todo {
  id: string;
  text: string;
  done: boolean;
}

export function TodoList({ userId }: { userId: string }) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [filter, setFilter] = useState<"all" | "active" | "done">("all");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/users/${userId}/todos`)
      .then((res) => res.json())
      .then((data: Todo[]) => {
        if (!cancelled) setTodos(data);
      })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [userId]);

  const toggleTodo = useCallback((id: string) => {
    setTodos((prev) =>
      prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t))
    );
  }, []);

  const filtered = useMemo(() => {
    if (filter === "active") return todos.filter((t) => !t.done);
    if (filter === "done") return todos.filter((t) => t.done);
    return todos;
  }, [todos, filter]);

  return (
    <div>
      <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
        <option value="all">All</option>
        <option value="active">Active</option>
        <option value="done">Done</option>
      </select>
      <ul>
        {filtered.map((t) => (
          <li key={t.id} onClick={() => toggleTodo(t.id)}>
            {t.done ? "✓" : "○"} {t.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
