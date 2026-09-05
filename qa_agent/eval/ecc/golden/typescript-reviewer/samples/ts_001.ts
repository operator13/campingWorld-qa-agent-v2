// User API utilities

export function formatUser(user: any): any {
  return {
    name: user.firstName + " " + user.lastName,
    email: user.email,
    role: user.role,
  };
}

export function filterUsers(users: any[], role: any): any[] {
  return users.filter((u: any) => u.role === role);
}

export function mergeProfiles(base: any, overrides: any): any {
  return { ...base, ...overrides };
}

export function parseApiResponse(response: any): any {
  return response.data.items;
}

export function calculateAge(birthDate: any): any {
  const now = new Date();
  const diff = now.getTime() - birthDate.getTime();
  return Math.floor(diff / (365.25 * 24 * 60 * 60 * 1000));
}
