"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ImageOff } from "lucide-react";
import { toast } from "sonner";
import { LockedBadge } from "@/components/plan/locked";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { api } from "@/lib/api";
import { CAPTION_PRESETS } from "@/lib/presets";
import { cn } from "@/lib/utils";

interface Brand {
  logo_key: string | null;
  logo_url: string | null;
  logo_position: "top-left" | "top-right";
  logo_opacity: number;
  handle: string;
  primary_color: string;
  caption_preset: string | null;
  progress_bar: boolean;
  available: boolean;
  saved: boolean;
}

export default function BrandPage() {
  const [b, setB] = useState<Brand | null>(null);
  const [draft, setDraft] = useState<Partial<Brand>>({});

  useEffect(() => {
    api<Brand>("/brand").then(setB).catch((e) => toast.error((e as Error).message));
  }, []);
  if (!b) return null;
  const v = { ...b, ...draft };
  const dirty = Object.keys(draft).length > 0;

  const save = async () => {
    try {
      const { logo_position, logo_opacity, handle, primary_color, caption_preset, progress_bar } = v;
      setB(await api<Brand>("/brand", { method: "PUT", json: { logo_position, logo_opacity, handle, primary_color, caption_preset, progress_bar } }));
      setDraft({});
      toast.success("Brand kit saved. Switch on “My brand kit” when you make videos.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid max-w-4xl gap-6">
      <PageHeader
        title="Brand kit"
        description="Your logo, @handle and colours, added to every video you make with “My brand kit” switched on."
        actions={<LockedBadge feature="brand_kit" />}
      />
      {!b.available && (
        <div className="rounded-xl border border-primary/40 bg-primary/5 p-4 text-sm">
          The brand kit is part of Pro.{" "}
          <Link href="/pricing" className="text-primary underline">
            See plans
          </Link>{" "}
          to put your logo on every video and remove the watermark.
        </div>
      )}
      <div className={cn("grid gap-6 md:grid-cols-[1fr_260px]", !b.available && "pointer-events-none opacity-60")}>
        <div className="grid gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Logo</CardTitle>
              <CardDescription>PNG with a transparent background looks best. Square or wide, at least 300 px.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {b.logo_url ? (
                <div className="flex items-center gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={b.logo_url} alt="Your logo" className="h-16 max-w-40 rounded border bg-[repeating-conic-gradient(#333_0%_25%,#222_0%_50%)] bg-[length:16px_16px] object-contain p-1" data-testid="logo-preview" />
                  <Button variant="ghost" size="sm" onClick={async () => setB(await api<Brand>("/brand/logo", { method: "DELETE" }))}>
                    <ImageOff /> Remove
                  </Button>
                </div>
              ) : null}
              <UploadDropzone
                purpose="image"
                label={b.logo_url ? "Replace logo" : "Upload your logo"}
                onComplete={async (u) => {
                  try {
                    setB(await api<Brand>("/brand/logo", { method: "PUT", json: { upload_id: u.id } }));
                    toast.success("Logo saved");
                  } catch (e) {
                    toast.error((e as Error).message);
                  }
                }}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Position">
                  <Select
                    value={v.logo_position}
                    onValueChange={(x) => setDraft((d) => ({ ...d, logo_position: x as Brand["logo_position"] }))}
                    options={[
                      { value: "top-right", label: "Top right" },
                      { value: "top-left", label: "Top left" },
                    ]}
                  />
                </Field>
                <Field label={`Opacity: ${Math.round(v.logo_opacity * 100)}%`}>
                  <Slider min={0.2} max={1} step={0.05} value={[v.logo_opacity]} onValueChange={([x]) => setDraft((d) => ({ ...d, logo_opacity: x }))} />
                </Field>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Style</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Handle (optional)" hint="Shown under the logo, e.g. @yourchannel">
                <Input value={v.handle} maxLength={40} onChange={(e) => setDraft((d) => ({ ...d, handle: e.target.value }))} placeholder="@yourchannel" aria-label="Handle" />
              </Field>
              <Field label="Brand colour" hint="Used for the progress bar">
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={v.primary_color}
                    onChange={(e) => setDraft((d) => ({ ...d, primary_color: e.target.value.toUpperCase() }))}
                    className="h-10 w-12 cursor-pointer rounded border bg-transparent"
                    aria-label="Brand colour"
                  />
                  <Input value={v.primary_color} onChange={(e) => setDraft((d) => ({ ...d, primary_color: e.target.value }))} className="w-28 font-mono" />
                </div>
              </Field>
              <Field label="Default caption style">
                <Select
                  value={v.caption_preset ?? "none_set"}
                  onValueChange={(x) => setDraft((d) => ({ ...d, caption_preset: x === "none_set" ? null : x }))}
                  options={[{ value: "none_set", label: "No default" }, ...Object.entries(CAPTION_PRESETS).map(([id, p]) => ({ value: id, label: p.label ?? id }))]}
                />
              </Field>
              <label className="flex items-center justify-between gap-3 self-end text-sm">
                <span>
                  Progress bar
                  <span className="block text-xs text-muted-foreground">Always add one</span>
                </span>
                <Switch checked={v.progress_bar} onCheckedChange={(x) => setDraft((d) => ({ ...d, progress_bar: x }))} aria-label="Progress bar" />
              </label>
            </CardContent>
          </Card>
          <div className="flex justify-end gap-2">
            {dirty && (
              <Button variant="ghost" onClick={() => setDraft({})}>
                Discard
              </Button>
            )}
            <Button onClick={save} disabled={!dirty && b.saved} data-testid="save-brand">
              Save brand kit
            </Button>
          </div>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium">Preview</p>
          <div className="relative aspect-[9/16] overflow-hidden rounded-xl border bg-gradient-to-b from-zinc-700 to-zinc-900" data-testid="brand-preview">
            {v.progress_bar && <div className="absolute left-0 top-0 h-1.5 w-2/5" style={{ background: v.primary_color }} />}
            <div className={cn("absolute top-[6%] flex flex-col gap-1", v.logo_position === "top-left" ? "left-[5%] items-start" : "right-[5%] items-end")}>
              {b.logo_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={b.logo_url} alt="" className="w-14 object-contain" style={{ opacity: v.logo_opacity }} />
              )}
              {v.handle && <span className="text-[10px] font-bold text-white/85 drop-shadow">{v.handle}</span>}
            </div>
            <p className="absolute inset-x-4 top-[68%] text-center text-lg font-black uppercase leading-tight text-white [text-shadow:0_2px_0_#000,0_0_6px_#000]">
              this is how <span className="text-[#FFE500]">it looks</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
