// React component with stale closure bug

import React, { useState, useEffect, useCallback } from "react";

export function Counter() {
  const [count, setCount] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTotal(count * 2);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleClick = useCallback(() => {
    setTimeout(() => {
      setTotal(count + 10);
    }, 2000);
  }, []);

  const logCount = useCallback(() => {
    console.log(`Current count is: ${count}`);
    fetch("/api/analytics", {
      method: "POST",
      body: JSON.stringify({ count }),
    });
  }, []);

  return (
    <div>
      <p>Count: {count}</p>
      <p>Total: {total}</p>
      <button onClick={() => setCount((c) => c + 1)}>Increment</button>
      <button onClick={handleClick}>Add 10 Later</button>
      <button onClick={logCount}>Log Count</button>
    </div>
  );
}
