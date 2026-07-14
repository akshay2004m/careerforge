'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async () => {
    if (!email || !password) {
      alert("Please enter email and password");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("token", data.access_token);
        router.push("/dashboard");
      } else {
        const errorData = await res.json();
        alert(errorData.detail || "Invalid email or password");
      }
    } catch {
      alert("Error connecting to backend server");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center text-white">
      <div className="bg-zinc-900 p-10 rounded-3xl w-full max-w-md border border-zinc-800">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold">Welcome back</h2>
          <p className="text-zinc-400 mt-2">Log in to continue your career journey</p>
        </div>

        <div className="space-y-4">
          <input
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 focus:border-purple-600 rounded-2xl px-5 py-3.5 outline-none"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 focus:border-purple-600 rounded-2xl px-5 py-3.5 outline-none"
          />
        </div>

        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full mt-6 bg-purple-600 hover:bg-purple-700 disabled:opacity-70 py-4 rounded-2xl font-semibold text-lg transition-all active:scale-[0.985]"
        >
          {loading ? "Logging in..." : "Log In"}
        </button>

        <p className="text-center mt-6 text-zinc-400">
          Don&apos;t have an account?{" "}
          <Link href="/auth/signup" className="text-purple-500 hover:underline font-medium">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
