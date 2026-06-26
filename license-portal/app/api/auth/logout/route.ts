import { NextRequest } from "next/server";
import { clearAuthResponse } from "@/lib/auth";
import { requireSameOrigin } from "@/lib/http";

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  return clearAuthResponse();
}
