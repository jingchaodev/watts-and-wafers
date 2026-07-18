import type { SignalEventsData } from "@/lib/types";
import StalePill from "./StalePill";

function humanize(s: string | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ");
}

export default function SignalEventsFeed({ signalEvents }: { signalEvents: SignalEventsData }) {
  const events = [...(signalEvents.events ?? [])].sort((a, b) =>
    (b.date ?? "").localeCompare(a.date ?? "")
  );

  return (
    <section className="block" id="signal-events">
      <h2 className="section-title">
        Signal events
        <StalePill asof={signalEvents.asof} hours={26} />
      </h2>
      <p className="section-sub">
        Percentile crossings, composite label flips, and single-week shocks — fired once per
        crossing, not every day it stays crossed.
      </p>
      <div className="card">
        {events.length === 0 ? (
          <p className="note-muted">No signal events in the recent window.</p>
        ) : (
          events.map((e, i) => (
            <div className="signal-event-row" key={`${e.date}-${e.signal}-${e.kind}-${i}`}>
              <span className="signal-event-date">{e.date ?? "—"}</span>
              <span className="signal-event-main">
                <span className="signal-event-signal">{humanize(e.signal)}</span>
                <span className="signal-event-detail">{e.detail ?? "—"}</span>
              </span>
              <span className="signal-event-kind">{humanize(e.kind as string)}</span>
            </div>
          ))
        )}
        {signalEvents.errors && signalEvents.errors.length > 0 && (
          <p className="note-muted">Collector errors: {signalEvents.errors.join("; ")}</p>
        )}
      </div>
    </section>
  );
}
