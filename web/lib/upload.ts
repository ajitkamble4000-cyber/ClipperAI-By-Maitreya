"use client";

import { api, ApiError } from "@/lib/api";

export type UploadPurpose = "source" | "voiceover" | "music" | "sfx" | "image";

export interface UploadInfo {
  id: string;
  filename: string;
  size: number;
  part_size: number;
  part_count: number;
  status: "uploading" | "complete" | "aborted";
  purpose: UploadPurpose;
  content_type: string;
  parts?: { part_number: number; etag: string; size: number }[];
}

export interface UploadProgress {
  loaded: number;
  total: number;
  bytesPerSecond: number;
}

const CONCURRENCY = 4;
const MAX_RETRIES = 5;

function storageKey(file: File, purpose: UploadPurpose) {
  return `upload:${purpose}:${file.name}:${file.size}:${file.lastModified}`;
}

function guessType(file: File): string {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase();
  const map: Record<string, string> = {
    mkv: "video/x-matroska", mov: "video/quicktime", mp4: "video/mp4", webm: "video/webm",
    mp3: "audio/mpeg", wav: "audio/wav", m4a: "audio/mp4", ogg: "audio/ogg",
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp",
  };
  return (ext && map[ext]) || "application/octet-stream";
}

function putPart(url: string, blob: Blob, onBytes: (n: number) => void, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let sent = 0;
    xhr.open("PUT", url);
    xhr.upload.onprogress = (e) => {
      onBytes(e.loaded - sent);
      sent = e.loaded;
    };
    xhr.onload = () => {
      const etag = xhr.getResponseHeader("ETag");
      if (xhr.status >= 200 && xhr.status < 300 && etag) resolve(etag);
      else {
        onBytes(-sent);
        reject(new Error(etag ? `Part upload failed (${xhr.status})` : "Storage did not return an ETag (check bucket CORS ExposeHeaders)"));
      }
    };
    xhr.onerror = () => {
      onBytes(-sent);
      reject(new Error("Network error"));
    };
    xhr.onabort = () => {
      onBytes(-sent);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(blob);
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Resumable browser -> R2 multipart upload. Survives page refreshes (pick the same file again). */
export class ResumableUpload {
  private controller = new AbortController();
  private loaded = 0;
  private startedAt = 0;
  private startLoaded = 0;

  constructor(
    public file: File,
    public purpose: UploadPurpose,
    private onProgress: (p: UploadProgress) => void,
  ) {}

  pause() {
    this.controller.abort();
  }

  async cancel(info?: UploadInfo) {
    this.controller.abort();
    localStorage.removeItem(storageKey(this.file, this.purpose));
    if (info) await api(`/uploads/${info.id}`, { method: "DELETE" }).catch(() => {});
  }

  private emit() {
    const secs = (performance.now() - this.startedAt) / 1000;
    this.onProgress({
      loaded: Math.max(0, this.loaded),
      total: this.file.size,
      bytesPerSecond: secs > 0.5 ? (this.loaded - this.startLoaded) / secs : 0,
    });
  }

  private async existing(): Promise<UploadInfo | null> {
    const id = localStorage.getItem(storageKey(this.file, this.purpose));
    if (!id) return null;
    try {
      const info = await api<UploadInfo>(`/uploads/${id}`);
      if (info.status === "aborted" || info.size !== this.file.size) return null;
      return info;
    } catch {
      return null;
    }
  }

  async start(): Promise<UploadInfo> {
    this.controller = new AbortController();
    const signal = this.controller.signal;
    let info = await this.existing();
    if (info?.status === "complete") return info;
    if (!info) {
      info = await api<UploadInfo>("/uploads", {
        method: "POST",
        json: { filename: this.file.name, size: this.file.size, content_type: guessType(this.file), purpose: this.purpose },
      });
      info.parts = [];
      localStorage.setItem(storageKey(this.file, this.purpose), info.id);
    }
    const etags = new Map<number, string>((info.parts ?? []).map((p) => [p.part_number, p.etag]));
    this.loaded = (info.parts ?? []).reduce((a, p) => a + p.size, 0);
    this.startLoaded = this.loaded;
    this.startedAt = performance.now();
    this.emit();

    const todo: number[] = [];
    for (let n = 1; n <= info.part_count; n++) if (!etags.has(n)) todo.push(n);
    const urls = new Map<number, string>();
    const sign = async (nums: number[]) => {
      const r = await api<{ urls: Record<string, string> }>(`/uploads/${info!.id}/parts`, {
        method: "POST",
        json: { part_numbers: nums },
      });
      Object.entries(r.urls).forEach(([k, v]) => urls.set(Number(k), v));
    };

    const worker = async () => {
      while (todo.length) {
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        const n = todo.shift()!;
        const start = (n - 1) * info!.part_size;
        const blob = this.file.slice(start, Math.min(start + info!.part_size, this.file.size));
        for (let attempt = 0; ; attempt++) {
          try {
            if (!urls.has(n)) await sign([n, ...todo.slice(0, 19)]);
            const etag = await putPart(urls.get(n)!, blob, (d) => { this.loaded += d; this.emit(); }, signal);
            etags.set(n, etag);
            break;
          } catch (e) {
            if ((e as Error).name === "AbortError" || attempt >= MAX_RETRIES) throw e;
            urls.delete(n); // URL may have expired
            await sleep(500 * 2 ** attempt);
          }
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, todo.length || 1) }, worker));

    try {
      const done = await api<UploadInfo>(`/uploads/${info.id}/complete`, {
        method: "POST",
        json: { parts: [...etags.entries()].map(([part_number, etag]) => ({ part_number, etag })) },
      });
      localStorage.removeItem(storageKey(this.file, this.purpose));
      return done;
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) localStorage.removeItem(storageKey(this.file, this.purpose));
      throw e;
    }
  }
}
