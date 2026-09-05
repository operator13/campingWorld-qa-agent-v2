// Proper async/await with error handling

interface ApiError {
  status: number;
  message: string;
}

type Result<T> = { ok: true; data: T } | { ok: false; error: ApiError };

async function safeFetch<T>(url: string): Promise<Result<T>> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return { ok: false, error: { status: response.status, message: response.statusText } };
    }
    const data: T = await response.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: { status: 0, message: err instanceof Error ? err.message : "Unknown error" } };
  }
}

export async function loadUser(id: string): Promise<Result<{ name: string; email: string }>> {
  return safeFetch(`/api/users/${id}`);
}

export async function loadWithRetry<T>(url: string, retries: number = 3): Promise<Result<T>> {
  for (let attempt = 0; attempt < retries; attempt++) {
    const result = await safeFetch<T>(url);
    if (result.ok) return result;
    if (attempt < retries - 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
    }
  }
  return { ok: false, error: { status: 0, message: `Failed after ${retries} retries` } };
}
