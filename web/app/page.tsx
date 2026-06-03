"use client";

import { useState } from "react";

type Snapshot = {
  life_stage: string;
  stated_goals: string[];
  risk_signals: string[];
  urgency: "low" | "medium" | "high";
};

type LedgerEntry = {
  span: string;
  classification: "information" | "guidance" | "advice" | "blocked";
  reason_code: string;
  detail: string;
  action: "allowed" | "annotated" | "redacted" | "blocked";
};

type AnalyzeResponse = {
  snapshot: Snapshot;
  adviser_agenda: string[];
  background_notes_safe: string;
  background_notes_raw: string;
  ledger: {
    entries: LedgerEntry[];
    counts: Record<string, number>;
  };
  model: string;
  used_mock: boolean;
};

const SAMPLE_TRANSCRIPT = `I'm 34, two kids, both under 7. Renting in south London — £1,750 a month. Take-home around £4,400 net. We've got about £8,000 in a savings account. Employer pension I get auto-enrolled in but I don't really understand what it's invested in. I keep hearing about a Help-to-Buy ISA, or maybe a Lifetime ISA — honestly I get the two confused. Goal is a house in maybe 4-5 years if we can stretch to it. What should we be thinking about?`;

export default function Page() {
  const [transcript, setTranscript] = useState(SAMPLE_TRANSCRIPT);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  async function analyze() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ transcript }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`API ${res.status}: ${body.slice(0, 200)}`);
      }
      setResult((await res.json()) as AnalyzeResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <Header />

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TranscriptPane
          transcript={transcript}
          onChange={setTranscript}
          onAnalyze={analyze}
          loading={loading}
        />
        <BriefPane
          result={result}
          loading={loading}
          error={error}
          showRaw={showRaw}
          onToggleRaw={() => setShowRaw((v) => !v)}
        />
      </div>

      <Footer />
    </main>
  );
}

function Header() {
  return (
    <header className="flex items-baseline justify-between border-b border-ink/10 pb-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">
          Cloven<span className="text-cloven-500">.</span>
        </h1>
        <p className="mt-1 text-sm text-ink/60">
          Adviser co-pilot with a deterministic compliance guardrail.
        </p>
      </div>
      <a
        href="https://github.com/"
        className="text-xs uppercase tracking-widest text-ink/40 hover:text-ink"
      >
        github
      </a>
    </header>
  );
}

function TranscriptPane({
  transcript,
  onChange,
  onAnalyze,
  loading,
}: {
  transcript: string;
  onChange: (s: string) => void;
  onAnalyze: () => void;
  loading: boolean;
}) {
  return (
    <section className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink/60">
          Client transcript
        </h2>
        <span className="text-xs text-ink/40">Synthetic — for demo only</span>
      </div>
      <textarea
        value={transcript}
        onChange={(e) => onChange(e.target.value)}
        className="mt-3 h-72 w-full resize-none rounded-lg border border-ink/15 bg-paper p-4 font-mono text-[13px] leading-6 focus:border-cloven-500 focus:outline-none"
      />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-ink/40">{transcript.length} chars</span>
        <button
          onClick={onAnalyze}
          disabled={loading || transcript.trim().length === 0}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-paper transition hover:bg-cloven-700 disabled:cursor-not-allowed disabled:bg-ink/30"
        >
          {loading ? "Analysing…" : "Analyse"}
        </button>
      </div>
    </section>
  );
}

function BriefPane({
  result,
  loading,
  error,
  showRaw,
  onToggleRaw,
}: {
  result: AnalyzeResponse | null;
  loading: boolean;
  error: string | null;
  showRaw: boolean;
  onToggleRaw: () => void;
}) {
  return (
    <section className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink/60">
          Adviser brief
        </h2>
        {result && (
          <div className="flex items-center gap-2 text-xs text-ink/50">
            <span className="rounded-full bg-cloven-50 px-2 py-0.5 text-cloven-700">
              {result.model}
            </span>
            <button
              onClick={onToggleRaw}
              className="rounded border border-ink/20 px-2 py-0.5 hover:bg-ink/5"
            >
              {showRaw ? "Hide raw LLM output" : "Show raw LLM output"}
            </button>
          </div>
        )}
      </div>

      <div className="mt-3 min-h-[18rem]">
        {error && (
          <p className="text-sm text-red-600">Error: {error}</p>
        )}
        {!result && !loading && !error && (
          <Placeholder />
        )}
        {loading && (
          <p className="text-sm text-ink/40">Running model + guardrail…</p>
        )}
        {result && <Brief result={result} showRaw={showRaw} />}
      </div>
    </section>
  );
}

function Placeholder() {
  return (
    <div className="rounded-lg border border-dashed border-ink/15 p-6 text-sm text-ink/50">
      Paste or edit a client transcript and click <strong>Analyse</strong>.
      You&rsquo;ll get a structured snapshot, a suggested adviser agenda, and a
      compliance ledger showing every claim the model surfaced — with anything
      that crossed the FCA advice line redacted before it reached this pane.
    </div>
  );
}

function Brief({
  result,
  showRaw,
}: {
  result: AnalyzeResponse;
  showRaw: boolean;
}) {
  const { snapshot, adviser_agenda, ledger } = result;
  const blocked = ledger.entries.filter((e) => e.action !== "allowed");

  return (
    <div className="space-y-6">
      <SnapshotBlock snapshot={snapshot} />
      <AgendaBlock items={adviser_agenda} />

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink/50">
          Background notes
          {blocked.length > 0 && (
            <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
              {blocked.length} redaction{blocked.length === 1 ? "" : "s"}
            </span>
          )}
        </h3>
        <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink/80">
          {result.background_notes_safe || (
            <span className="text-ink/40">No background notes returned.</span>
          )}
        </p>
        {showRaw && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-amber-700">
              Raw LLM output (pre-guardrail)
            </div>
            <p className="whitespace-pre-line leading-relaxed">
              {result.background_notes_raw}
            </p>
          </div>
        )}
      </div>

      <LedgerBlock ledger={ledger} />
    </div>
  );
}

function SnapshotBlock({ snapshot }: { snapshot: Snapshot }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink/50">
        Client snapshot
      </h3>
      <dl className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Life stage" value={snapshot.life_stage} />
        <Field label="Urgency" value={snapshot.urgency} mono />
        <ListField label="Goals" items={snapshot.stated_goals} />
        <ListField label="Risk signals" items={snapshot.risk_signals} />
      </dl>
    </div>
  );
}

function AgendaBlock({ items }: { items: string[] }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink/50">
        Suggested adviser agenda
      </h3>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink/80">
        {items.map((q, i) => (
          <li key={i}>{q}</li>
        ))}
      </ol>
    </div>
  );
}

function LedgerBlock({
  ledger,
}: {
  ledger: AnalyzeResponse["ledger"];
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink/50">
        Compliance ledger
      </h3>
      <div className="mt-2 flex gap-2 text-[11px]">
        <Badge label="info" count={ledger.counts.information} tone="neutral" />
        <Badge label="guidance" count={ledger.counts.guidance} tone="blue" />
        <Badge label="advice" count={ledger.counts.advice} tone="amber" />
        <Badge label="blocked" count={ledger.counts.blocked} tone="red" />
      </div>
      <ul className="mt-3 space-y-2">
        {ledger.entries.map((entry, i) => (
          <LedgerRow key={i} entry={entry} />
        ))}
      </ul>
    </div>
  );
}

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const tone = toneFor(entry.classification);
  return (
    <li className={`rounded-md border p-3 text-xs ${tone.border} ${tone.bg}`}>
      <div className="flex items-center justify-between gap-3">
        <span className={`font-mono uppercase tracking-wider ${tone.text}`}>
          {entry.classification}
        </span>
        <span className="text-ink/40 font-mono">{entry.reason_code}</span>
      </div>
      <blockquote className="mt-1 text-ink/80 leading-relaxed">
        “{entry.span}”
      </blockquote>
      <p className="mt-1 text-[11px] text-ink/55">{entry.detail}</p>
    </li>
  );
}

function toneFor(c: LedgerEntry["classification"]) {
  switch (c) {
    case "information":
      return { border: "border-ink/10", bg: "bg-ink/[0.02]", text: "text-ink/60" };
    case "guidance":
      return { border: "border-blue-200", bg: "bg-blue-50", text: "text-blue-700" };
    case "advice":
      return { border: "border-amber-300", bg: "bg-amber-50", text: "text-amber-800" };
    case "blocked":
      return { border: "border-red-300", bg: "bg-red-50", text: "text-red-700" };
  }
}

function Badge({
  label,
  count,
  tone,
}: {
  label: string;
  count: number;
  tone: "neutral" | "blue" | "amber" | "red";
}) {
  const toneClasses: Record<typeof tone, string> = {
    neutral: "bg-ink/10 text-ink/70",
    blue: "bg-blue-100 text-blue-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-800",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 font-mono ${toneClasses[tone]}`}>
      {label} {count}
    </span>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] font-semibold uppercase tracking-widest text-ink/40">
        {label}
      </dt>
      <dd className={`mt-0.5 text-sm text-ink/80 ${mono ? "font-mono" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

function ListField({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="sm:col-span-2">
      <dt className="text-[10px] font-semibold uppercase tracking-widest text-ink/40">
        {label}
      </dt>
      <dd className="mt-0.5">
        <ul className="list-disc space-y-0.5 pl-5 text-sm text-ink/80">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

function Footer() {
  return (
    <footer className="mt-12 border-t border-ink/10 pt-6 text-xs text-ink/40">
      <p>
        All transcripts in this demo are <strong>synthetic</strong>. Cloven is a
        portfolio project and is <strong>not</strong> a regulated financial
        adviser. Outputs are post-processed by a deterministic guardrail before
        leaving the server. See README for the full architecture.
      </p>
    </footer>
  );
}
