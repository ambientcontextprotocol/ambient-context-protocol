import { name } from '@/lib/name';

type Box = { title: string; detail: string };

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

function Column({ label, boxes }: { label: string; boxes: Box[] }) {
  return (
    <div className="flex flex-col gap-3">
      {boxes.map((box) => (
        <div key={box.title} className="rounded-lg border border-fd-border bg-fd-muted px-2 py-2.5 text-center">
          <div className="text-sm font-medium text-fd-foreground">{box.title}</div>
          <div className="text-xs text-fd-muted-foreground">{box.detail}</div>
        </div>
      ))}
      <div className="text-center text-xs text-fd-muted-foreground">{label}</div>
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex flex-col items-center justify-center gap-1 text-fd-muted-foreground">
      <svg viewBox="0 0 40 12" className="hidden h-3 w-10 md:block" aria-hidden="true">
        <path d="M0 6h36M30 1l6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.2" />
      </svg>
      <svg viewBox="0 0 12 32" className="h-8 w-3 md:hidden" aria-hidden="true">
        <path d="M6 0v28M1 22l5 6 5-6" fill="none" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    </div>
  );
}

/** The Introduction's overview: apps on the left answer, the protocol in the middle, hosts on the right ask. */
export function OverviewDiagram() {
  return (
    <figure className="not-prose my-8 rounded-xl border border-fd-border p-4 sm:p-6">
      <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)]">
        <Column label="Providers: the apps the user works in. They answer what is open and selected, and where." boxes={providers} />
        <Arrow />
        <div className="rounded-lg border border-fd-foreground/30 bg-fd-accent px-3 py-6 text-center">
          <div className="text-sm font-semibold text-fd-foreground">{name}</div>
          <div className="mb-3 text-xs text-fd-muted-foreground">An extension to MCP</div>
          <div className="flex flex-col gap-1 font-mono text-[11px] text-fd-foreground/80">
            <span>ambient://current</span>
            <span className="break-all">ambient://location/{'{id}'}</span>
          </div>
        </div>
        <Arrow />
        <Column label="Hosts: MCP clients. They read when the user asks." boxes={hosts} />
      </div>
    </figure>
  );
}
