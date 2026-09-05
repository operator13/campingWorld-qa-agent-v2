// Well-typed utility with generics and proper null handling

interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "member" | "guest";
}

export function paginate<T>(items: T[], page: number, pageSize: number): PaginatedResult<T> {
  const start = (page - 1) * pageSize;
  const sliced = items.slice(start, start + pageSize);
  return { items: sliced, total: items.length, page, pageSize };
}

export function findById<T extends { id: string }>(
  items: T[],
  id: string
): T | undefined {
  return items.find((item) => item.id === id);
}

export function safeGetName(user: User | null | undefined): string {
  return user?.name ?? "Unknown";
}

export function groupByRole(users: User[]): Map<User["role"], User[]> {
  const groups = new Map<User["role"], User[]>();
  for (const user of users) {
    const existing = groups.get(user.role) ?? [];
    groups.set(user.role, [...existing, user]);
  }
  return groups;
}
