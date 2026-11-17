import { ProtocolLogo } from '@/components/protocol-logo';
import { name } from '@/lib/name';

type Box = { title: string; detail: string };

// The protocol is blue; the providers and hosts around it stay neutral.
type Tone = { box: string; title: string; caption: string };

const neutral: Tone = {
  box: 'border-fd-border bg-fd-muted',
  title: 'text-fd-foreground',
  caption: 'text-fd-muted-foreground',
};

// Arrows run from neutral gray into Tailwind's sky-400 and back out.
const gray = '#71717a';
const sky = '#38bdf8';

const providers: Box[] = [
  { title: 'Editors', detail: 'Paper, code editors' },
  { title: 'Design tools', detail: 'Canvases, frames, layers' },
  { title: 'Task and mail apps', detail: 'Lists, threads, messages' },
];

const hosts: Box[] = [
  { title: 'Ambient assistants', detail: 'Sirius' },
  { title: 'Any MCP client', detail: 'Lists and reads the two resources' },
  { title: 'The agent', detail: 'Sees only what the host passes on' },
];

function Column({ label, boxes, tone }: { label: string; boxes: Box[]; tone: Tone }) {
  return (
    <div className="flex flex-col gap-3">
      {boxes.map((box) => (
        <div key={box.title} className={`rounded-lg border px-2 py-2.5 text-center ${tone.box}`}>
          <div className={`text-sm font-medium ${tone.title}`}>{box.title}</div>
          <div className="text-xs text-fd-muted-foreground">{box.detail}</div>
        </div>
      ))}
      <div className={`text-center text-xs ${tone.caption}`}>{label}</div>
    </div>
  );
}

function Arrow({ id, from, to }: { id: string; from: string; to: string }) {
  return (
    <div className="flex items-center justify-center">
      <svg viewBox="0 0 40 12" className="hidden h-3 w-10 md:block" aria-hidden="true">
        <defs>
          <linearGradient id={`${id}-h`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor={from} />
            <stop offset="1" stopColor={to} />
          </linearGradient>
        </defs>
        <path d="M0 6h36M30 1l6 5-6 5" fill="none" stroke={`url(#${id}-h)`} strokeWidth="1.5" />
      </svg>
      <svg viewBox="0 0 12 32" className="h-8 w-3 md:hidden" aria-hidden="true">
        <defs>
          <linearGradient id={`${id}-v`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={from} />
            <stop offset="1" stopColor={to} />
          </linearGradient>
        </defs>
        <path d="M6 0v28M1 22l5 6 5-6" fill="none" stroke={`url(#${id}-v)`} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

/** The Introduction's overview: apps on the left answer, the protocol in the middle, hosts on the right ask. */
export function OverviewDiagram() {
  return (
    <figure className="not-prose my-8 rounded-xl border border-fd-border p-4 sm:p-6">
      <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(12rem,1.1fr)_auto_minmax(0,1fr)]">
        <Column label="Providers: the apps the user works in. They answer what is open and selected, and where." boxes={providers} tone={neutral} />
        <Arrow id="arrow-in" from={gray} to={sky} />
        <div className="rounded-lg border border-sky-400/50 bg-sky-500/15 px-3 py-6 text-center shadow-[0_0_32px_-8px_rgba(56,189,248,0.35)]">
          <ProtocolLogo className="mx-auto mb-3 h-8 w-8 text-sky-200" />
          <div className="text-sm font-semibold text-sky-100">{name}</div>
          <div className="mb-3 text-xs text-sky-300/80">An extension to MCP</div>
          <div className="flex flex-col gap-1 whitespace-nowrap font-mono text-[11px] text-sky-100/90">
            <span>ambient://current</span>
            <span>ambient://location/{'{id}'}</span>
          </div>
        </div>
        <Arrow id="arrow-out" from={sky} to={gray} />
        <Column label="Hosts: MCP clients. They read when the user asks." boxes={hosts} tone={neutral} />
      </div>
    </figure>
  );
}
