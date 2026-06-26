import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    {
      error: "Endpoint de validation obsolete desactive. Utilisez /api/license/validate."
    },
    { status: 410 }
  );
}
