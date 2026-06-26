import { Suspense } from "react";
import { AuthForm } from "@/components/AuthForm";

export default async function ResetPasswordPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;

  return (
    <Suspense>
      <AuthForm mode="reset" token={token} />
    </Suspense>
  );
}
