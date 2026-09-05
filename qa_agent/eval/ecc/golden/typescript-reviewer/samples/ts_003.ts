// Data transformation utilities

interface ApiResponse {
  status: number;
  payload: unknown;
}

export function extractUsers(response: ApiResponse): { name: string; id: number }[] {
  const data = response.payload as any;
  return data.users as { name: string; id: number }[];
}

export function parseConfig(raw: unknown): Record<string, string> {
  return raw as Record<string, string>;
}

export function getNestedValue(obj: unknown, key: string): string {
  const typed = obj as any;
  return typed[key] as string;
}

export function transformEvent(event: Event): { x: number; y: number } {
  const mouseEvent = event as any as MouseEvent;
  return { x: mouseEvent.clientX, y: mouseEvent.clientY };
}

export function coerceId(value: string | number): number {
  return value as unknown as number;
}
