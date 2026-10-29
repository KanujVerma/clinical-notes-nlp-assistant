import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PublicShowcaseEvidence } from "../api/client";

function rate(value: number | null): string {
  return value === null ? "N/A" : (100 * value).toFixed(2) + "%";
}

/** Displays only committed and checked synthetic development evidence. */
export default function EvidenceShowcase() {
  const [evidence, setEvidence] = useState<PublicShowcaseEvidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let current = true;
    api.getPublicShowcaseEvidence()
      .then((result) => { if (current) setEvidence(result); })
      .catch((reason: unknown) => {
        if (current) setError(reason instanceof Error ? reason.message : "Evidence unavailable.");
      })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-cyan-700">Validation workbench · recorded evidence</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Synthetic evidence showcase</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Review a measured OCR development baseline and see which AI experiments have
            actually been recorded. All examples are synthetic. Matching model predictions
            do not establish clinical correctness or independently verify original pixels.
          </p>
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            <Link to="/queue" className="rounded-md bg-cyan-700 px-3 py-2 font-medium text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600">
              Open review queue
            </Link>
            <Link to="/metrics" className="rounded-md border border-slate-300 px-3 py-2 font-medium text-slate-700 hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600">
              Explore review metrics
            </Link>
          </div>
        </div>

        {loading && <p role="status" className="text-sm text-slate-600">Loading verified evidence…</p>}
        {error && <p role="alert" className="text-sm font-medium text-rose-700">{error}</p>}

        {evidence && (
          <>
            <section aria-labelledby="tesseract-heading" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 id="tesseract-heading" className="text-lg font-semibold text-slate-900">Recorded Tesseract OCR baseline</h2>
                  <p className="mt-1 text-xs text-slate-600">
                    Actually executed on generator-produced printed images. Engine version {evidence.baseline.engine_version}.
                  </p>
                </div>
                <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800">
                  Measured development output
                </span>
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["Cases", String(evidence.baseline.case_count)],
                  ["Character error", rate(evidence.baseline.cer_micro)],
                  ["Word error", rate(evidence.baseline.wer_micro)],
                  ["Critical-token hits", String(evidence.baseline.critical_token_hits) + "/" + String(evidence.baseline.critical_token_total)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-slate-200 p-3">
                    <dt className="text-xs text-slate-600">{label}</dt>
                    <dd className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs leading-relaxed text-slate-600">
                {evidence.baseline.limitations} A critical-token hit checks literal recognition,
                not whether the medication or negation was attributed correctly.
              </p>

              <h3 className="mt-5 text-sm font-semibold text-slate-800">Inspect actual saved transcriptions</h3>
              <div className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {evidence.baseline.cases.map((sample) => (
                  <details key={sample.case_id} className="group px-4 py-3">
                    <summary className="cursor-pointer list-inside text-sm font-semibold text-slate-800 focus-visible:outline-2 focus-visible:outline-cyan-600">
                      {sample.case_id.replace(/_/g, " ")}
                      <span className="ml-2 font-normal text-slate-600">
                        CER {rate(sample.cer)}, WER {rate(sample.wer)}
                      </span>
                    </summary>
                    <p className="my-2 break-all font-mono text-[11px] text-slate-500">
                      Source SHA-256: {sample.source_sha256}
                    </p>
                    <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-100 p-3 text-xs text-slate-800" aria-label={"Recorded OCR transcript for " + sample.case_id}>
                      {sample.transcription}
                    </pre>
                    <ul aria-label="Critical-token checks" className="mt-2 flex flex-wrap gap-2">
                      {sample.critical_tokens.map((item, index) => (
                        <li
                          key={item.token + index}
                          className={"rounded px-2 py-1 text-xs font-medium " + (item.recognized ? "bg-slate-100 text-slate-700" : "bg-rose-100 text-rose-800")}
                        >
                          {item.token}: {item.recognized ? "recognized" : "missed"}
                        </li>
                      ))}
                    </ul>
                  </details>
                ))}
              </div>
            </section>

            <section aria-labelledby="recorded-ai-heading" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 id="recorded-ai-heading" className="text-lg font-semibold text-slate-900">
                Recorded GLM-OCR / Qwen3-VL proposals
              </h2>
              {evidence.recorded_ai.status === "not_recorded" ? (
                <div className="mt-3 space-y-2">
                  <p className="text-sm text-slate-700">No reviewed local-model recordings are published.</p>
                  <p className="text-xs leading-relaxed text-slate-600">
                    The infrastructure is implemented, but the models were not installed during the last
                    local verification. This page does not substitute mocked predictions for evidence.
                  </p>
                </div>
              ) : (
                <div className="mt-3 space-y-4">
                  <p className="text-xs leading-relaxed text-slate-600">{evidence.recorded_ai.message}</p>
                  {evidence.recorded_ai.models.map((model) => (
                    <article key={model.adapter} className="rounded-lg border border-slate-200 p-3">
                      <h3 className="text-sm font-semibold text-slate-800">{model.adapter.replace(/_/g, "-")}</h3>
                      <p className="mt-1 break-all font-mono text-[11px] text-slate-500">Installed model digest: {model.model_digest}</p>
                      <div className="mt-3 divide-y divide-slate-100">
                        {model.cases.map((item) => (
                          <details key={item.case_id} className="py-2">
                            <summary className="cursor-pointer text-sm text-slate-800">{item.case_id.replace(/_/g, " ")}</summary>
                            <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words bg-slate-100 p-3 text-xs text-slate-700">
                              {item.transcription ?? JSON.stringify(item.structured_candidates, null, 2)}
                            </pre>
                          </details>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <p className="text-xs leading-relaxed text-slate-600">
              Evidence dataset manifest: <span className="break-all font-mono">{evidence.baseline.manifest_sha256}</span>.
              These are synthetic development records, not a held-out, clinically adjudicated
              benchmark. Model proposals must remain separate from human-verified review state.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
