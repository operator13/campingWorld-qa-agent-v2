// Data fetching service

interface User {
  id: number;
  name: string;
  email: string;
}

async function fetchUser(id: number): Promise<User> {
  const response = await fetch(`/api/users/${id}`);
  return response.json();
}

async function fetchAllUsers(): Promise<User[]> {
  const response = await fetch("/api/users");
  return response.json();
}

export function loadUserProfile(userId: number): void {
  const user = fetchUser(userId);
  console.log(`Loaded user: ${user}`);
}

export function syncUsers(): User[] {
  const users = fetchAllUsers();
  return users;
}

export async function updateAndReload(userId: number, data: Partial<User>): Promise<User> {
  fetch(`/api/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
  return fetchUser(userId);
}
