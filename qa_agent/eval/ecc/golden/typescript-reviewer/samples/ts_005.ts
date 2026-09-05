// Notification service with unhandled promise rejections

interface Notification {
  id: string;
  message: string;
  channel: "email" | "sms" | "push";
}

function sendEmail(to: string, message: string): Promise<void> {
  return fetch("/api/email", {
    method: "POST",
    body: JSON.stringify({ to, message }),
  }).then((res) => {
    if (!res.ok) throw new Error(`Email failed: ${res.status}`);
  });
}

export function notifyUser(userId: string, message: string): void {
  fetch(`/api/users/${userId}`)
    .then((res) => res.json())
    .then((user) => {
      sendEmail(user.email, message);
    });
}

export function broadcastNotification(userIds: string[], message: string): void {
  userIds.forEach((id) => {
    fetch(`/api/notify/${id}`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }).then((res) => res.json());
  });
}

export function loadAndDisplay(url: string): void {
  fetch(url)
    .then((res) => res.json())
    .then((data) => document.getElementById("output")!.textContent = JSON.stringify(data));
}
