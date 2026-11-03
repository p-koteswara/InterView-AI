export type HealthResponse = {
  status: string;
  service: string;
  database: string;
};

export function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  return baseUrl.replace(/\/$/, "");
}

export async function fetchHealth(): Promise<HealthResponse> {
  const url = `${getApiBaseUrl()}/api/health`;
  const response = await fetch(url, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}
