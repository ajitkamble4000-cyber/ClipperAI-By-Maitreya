"use client";

import { useState } from "react";
import { CalendarPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { go } from "@/lib/routes";

export const PLATFORMS = [
  { value: "youtube", label: "YouTube Shorts", color: "bg-red-500" },
  { value: "tiktok", label: "TikTok", color: "bg-cyan-400" },
  { value: "instagram", label: "Instagram Reels", color: "bg-pink-500" },
  { value: "facebook", label: "Facebook", color: "bg-blue-500" },
  { value: "x", label: "X", color: "bg-zinc-300" },
  { value: "linkedin", label: "LinkedIn", color: "bg-sky-600" },
  { value: "other", label: "Other", color: "bg-amber-400" },
];

function localInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Plan when a clip (or story) goes out, on which platform, with the post text. */
export function ScheduleButton({ clipId, projectId, defaultCaption, size = "sm" }: { clipId?: string; projectId?: string; defaultCaption?: string; size?: "sm" | "default" }) {
  const [open, setOpen] = useState(false);
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000);
  tomorrow.setMinutes(0, 0, 0);
  const [platform, setPlatform] = useState("youtube");
  const [when, setWhen] = useState(localInput(tomorrow));
  const [caption, setCaption] = useState(defaultCaption ?? "");
  const [remind, setRemind] = useState("30");

  const save = async () => {
    try {
      await api("/calendar", {
        method: "POST",
        json: { clip_id: clipId, project_id: clipId ? undefined : projectId, platform, scheduled_at: new Date(when).toISOString(), caption, remind_minutes: Number(remind) },
      });
      toast.success("Added to your calendar", { action: { label: "Open", onClick: () => go("/calendar") } });
      setOpen(false);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Button size={size} variant="outline" onClick={() => (setCaption(defaultCaption ?? ""), setOpen(true))} data-testid="schedule">
        <CalendarPlus /> Schedule
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>Schedule a post</DialogTitle>
          <DialogDescription>Plan it on your content calendar. We&apos;ll remind you when it&apos;s time to post.</DialogDescription>
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Platform">
                <Select value={platform} onValueChange={setPlatform} aria-label="Platform" options={PLATFORMS.map(({ value, label }) => ({ value, label }))} />
              </Field>
              <Field label="When">
                <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="When" />
              </Field>
            </div>
            <Field label="Post text">
              <Textarea rows={4} value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={2200} aria-label="Post text" />
            </Field>
            <Field label="Reminder">
              <Select
                value={remind}
                onValueChange={setRemind}
                aria-label="Reminder"
                options={[
                  { value: "0", label: "No reminder" },
                  { value: "15", label: "15 minutes before" },
                  { value: "30", label: "30 minutes before" },
                  { value: "60", label: "1 hour before" },
                  { value: "1440", label: "1 day before" },
                ]}
              />
            </Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} data-testid="save-schedule">
              Add to calendar
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
