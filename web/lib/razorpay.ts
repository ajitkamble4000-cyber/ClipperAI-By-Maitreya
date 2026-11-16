"use client";

import { api } from "@/lib/api";
import { BRAND } from "@/lib/brand";

/** What can be bought online (GET /public/billing). Prices are whole rupees. */
export interface BillingCatalog {
  enabled: boolean;
  key_id: string | null;
  currency: string;
  plans: { id: string; name: string; price_inr_month: number; price_inr_year: number }[];
  packs: { id: string; name: string; tokens: number; price_inr: number }[];
}

export type Purchase = { kind: "plan"; plan_id: string; period: "month" | "year" } | { kind: "tokens"; pack_id: string };

export interface PaidResult {
  status: "paid";
  description: string;
  until?: string;
  tokens?: number;
}

interface CheckoutOrder {
  order_id: string;
  key_id: string;
  amount: number;
  currency: string;
  description: string;
  prefill: { email: string; name: string };
}

interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void; on: (event: string, cb: (r: { error?: { description?: string } }) => void) => void };
  }
}

export const inr = (rupees: number) => `₹${rupees.toLocaleString("en-IN")}`;

let loading: Promise<void> | null = null;
function loadCheckout(): Promise<void> {
  if (typeof window !== "undefined" && window.Razorpay) return Promise.resolve();
  loading ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loading = null;
      reject(new Error("Couldn't load Razorpay. Check your connection and try again."));
    };
    document.body.appendChild(s);
  });
  return loading;
}

/**
 * Pay with Razorpay Checkout: creates the order on our server, opens Razorpay, then has the server verify the
 * signature and apply the purchase. Resolves when the purchase is applied; rejects with a readable message.
 */
export async function payWithRazorpay(purchase: Purchase): Promise<PaidResult> {
  const order = await api<CheckoutOrder>("/billing/checkout", { method: "POST", json: purchase });
  await loadCheckout();
  if (!window.Razorpay) throw new Error("Razorpay didn't load");
  return new Promise<PaidResult>((resolve, reject) => {
    const rzp = new window.Razorpay!({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount,
      currency: order.currency,
      name: BRAND,
      description: order.description,
      prefill: order.prefill,
      theme: { color: "#e472dc" },
      handler: (r: RazorpayResponse) => {
        api<PaidResult>("/billing/confirm", { method: "POST", json: r }).then(resolve, reject);
      },
      modal: { ondismiss: () => reject(new Error("Payment cancelled")) },
    });
    rzp.on("payment.failed", (r) => reject(new Error(r.error?.description || "The payment failed. No money was taken.")));
    rzp.open();
  });
}
