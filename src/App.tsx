import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  BarChart3,
  BriefcaseBusiness,
  CircleHelp,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import "./App.css";

const SkillChart = lazy(() => import("./SkillChart"));

type Skill = {
  name: string;
  offer_count: number;
  percentage: number;
};
type Education = { level: string; offer_count: number; percentage: number };
type Analysis = {
  query: string;
  generated_at: string;
  cached: boolean;
  total_offers: number;
  usable_offers: number;
  coverage_percentage: number;
  skills: Skill[];
  education_levels: Education[];
};
type Suggestion = { label: string; code: string };

const API_URL = (import.meta.env.VITE_API_URL ?? "")
  .replace(/\/api\/?$/, "")
  .replace(/\/$/, "");
const BUILD_ID = import.meta.env.VITE_BUILD_ID;

function App() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showMethod, setShowMethod] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const jobRequestRef = useRef<AbortController | null>(null);
  const analysisRequestRef = useRef<AbortController | null>(null);
  const jobFieldRef = useRef<HTMLDivElement | null>(null);
  const resultsRef = useRef<HTMLElement | null>(null);
  const methodTriggerRef = useRef<HTMLButtonElement | null>(null);
  const methodModalRef = useRef<HTMLElement | null>(null);
  const methodCloseRef = useRef<HTMLButtonElement | null>(null);

  const topSkill = analysis?.skills[0];
  const chartData = useMemo(
    () =>
      analysis?.skills
        .slice(0, 10)
        .map((skill) => ({ ...skill, shortName: skill.name })) ?? [],
    [analysis],
  );

  const updateQuery = (value: string) => {
    setQuery(value);
    setAnalysis(null);
    setError("");
    analysisRequestRef.current?.abort();
    setShowSuggestions(value.trim().length >= 2);
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    jobRequestRef.current?.abort();
    if (value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    debounceRef.current = window.setTimeout(async () => {
      const controller = new AbortController();
      jobRequestRef.current = controller;
      try {
        const response = await fetch(
          `${API_URL}/api/jobs?q=${encodeURIComponent(value)}`,
          { signal: controller.signal },
        );
        const payload = await response.json();
        if (!response.ok)
          throw new Error(
            payload.detail || "Recherche des métiers indisponible.",
          );
        setSuggestions(payload);
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setSuggestions([]);
        }
      }
    }, 650);
  };

  const runAnalysis = async (event?: FormEvent) => {
    event?.preventDefault();
    if (query.trim().length < 2) return;
    analysisRequestRef.current?.abort();
    const controller = new AbortController();
    analysisRequestRef.current = controller;
    setLoading(true);
    setAnalysis(null);
    setError("");
    setShowSuggestions(false);
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          query: query.trim(),
        }),
      });
      const isJson = response.headers
        .get("content-type")
        ?.includes("application/json");
      const payload = isJson ? await response.json() : null;
      if (!response.ok) {
        if (response.status === 504)
          throw new Error(
            "L'analyse prend plus de temps que prévu. Réessayez dans quelques instants.",
          );
        throw new Error(payload?.detail || "L'analyse n'a pas pu aboutir.");
      }
      if (!payload)
        throw new Error("Le serveur a renvoyé une réponse inattendue.");
      setAnalysis(payload);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(
        caught instanceof Error
          ? caught.message
          : "Une erreur inattendue est survenue.",
      );
    } finally {
      if (analysisRequestRef.current === controller) {
        analysisRequestRef.current = null;
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const closeSuggestions = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!jobFieldRef.current?.contains(target)) setShowSuggestions(false);
    };
    document.addEventListener("pointerdown", closeSuggestions);
    return () => document.removeEventListener("pointerdown", closeSuggestions);
  }, []);

  useEffect(() => {
    if (!showMethod) return;
    const body = document.body;
    const root = document.documentElement;
    const scrollPosition = window.scrollY;
    const previousStyles = {
      overflow: body.style.overflow,
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
      scrollBehavior: root.style.scrollBehavior,
    };
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.top = `-${scrollPosition}px`;
    body.style.width = "100%";
    const focusFrame = window.requestAnimationFrame(() => {
      const closeButton = methodCloseRef.current;
      if (!closeButton) return;
      closeButton.classList.add("programmatic-focus");
      closeButton.addEventListener(
        "blur",
        () => closeButton.classList.remove("programmatic-focus"),
        { once: true },
      );
      closeButton.focus();
    });
    const handleModalKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowMethod(false);
        return;
      }
      if (event.key !== "Tab" || !methodModalRef.current) return;
      methodCloseRef.current?.classList.remove("programmatic-focus");
      const focusableElements = Array.from(
        methodModalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!focusableElements.length) return;
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };
    document.addEventListener("keydown", handleModalKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleModalKeyDown);
      body.style.overflow = previousStyles.overflow;
      body.style.position = previousStyles.position;
      body.style.top = previousStyles.top;
      body.style.width = previousStyles.width;
      root.style.scrollBehavior = "auto";
      window.scrollTo(0, scrollPosition);
      root.style.scrollBehavior = previousStyles.scrollBehavior;
      const trigger = methodTriggerRef.current;
      if (trigger) {
        trigger.classList.add("programmatic-focus");
        trigger.addEventListener(
          "blur",
          () => trigger.classList.remove("programmatic-focus"),
          { once: true },
        );
        trigger.focus({ preventScroll: true });
      }
    };
  }, [showMethod]);

  useEffect(
    () => () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      jobRequestRef.current?.abort();
      analysisRequestRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    if (!loading) return;
    const frame = window.requestAnimationFrame(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loading]);

  useEffect(() => {
    let reloading = false;
    const checkForUpdate = async () => {
      if (reloading || loading || document.visibilityState === "hidden") return;
      try {
        const response = await fetch(`/version.json?t=${Date.now()}`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const version = (await response.json()) as { buildId?: string };
        if (version.buildId && version.buildId !== BUILD_ID) {
          reloading = true;
          window.location.reload();
        }
      } catch {
        return;
      }
    };
    const checkWhenVisible = () => {
      if (document.visibilityState === "visible") void checkForUpdate();
    };
    const interval = window.setInterval(() => void checkForUpdate(), 60_000);
    window.addEventListener("focus", checkForUpdate);
    document.addEventListener("visibilitychange", checkWhenVisible);
    void checkForUpdate();
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", checkForUpdate);
      document.removeEventListener("visibilitychange", checkWhenVisible);
    };
  }, [loading]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SkillScope, accueil">
          <img className="brand-logo" src="/SkillScope.svg" alt="SkillScope" />
        </a>
        <div className="topbar-actions">
          <button
            ref={methodTriggerRef}
            className="text-button"
            type="button"
            onClick={() => setShowMethod(true)}
          >
            <CircleHelp size={17} /> Méthodologie
          </button>
        </div>
      </header>

      <main id="top">
        <section>
          <div className="eyebrow">
            <span /> Observatoire des compétences
          </div>
          <div className="title-row">
            <h1>
              Ce que le marché
              <br />
              demande vraiment.
            </h1>
            <p className="intro-copy">
              SkillScope analyse les offres d’emploi pour faire ressortir les
              compétences les plus demandées pour un métier.
            </p>
            <p className="ai-warning">
              Les résultats sont générés avec Gemini, l’intelligence
              artificielle de Google. Ils peuvent donc contenir certaines
              imprécisions.
            </p>
          </div>

          <form className="search-panel" onSubmit={runAnalysis}>
            <div className="field" ref={jobFieldRef}>
              <div className="input-wrap">
                <Search size={20} />
                <input
                  id="job"
                  role="combobox"
                  aria-autocomplete="list"
                  aria-haspopup="listbox"
                  aria-controls="job-suggestions"
                  aria-expanded={showSuggestions && query.trim().length >= 2}
                  value={query}
                  onChange={(e) => updateQuery(e.target.value)}
                  onFocus={() => setShowSuggestions(query.length >= 2)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setShowSuggestions(false);
                  }}
                  autoComplete="off"
                  placeholder=" "
                />
                <label className="floating-label" htmlFor="job">
                  Rechercher un métier
                </label>
                {query && (
                  <button
                    type="button"
                    aria-label="Effacer"
                    onClick={() => updateQuery("")}
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
              {showSuggestions && query.trim().length >= 2 && (
                <div
                  className="suggestions"
                  id="job-suggestions"
                  role="listbox"
                  aria-label="Suggestions de métiers"
                >
                  <button
                    type="button"
                    role="option"
                    aria-selected="false"
                    onClick={() => {
                      analysisRequestRef.current?.abort();
                      setShowSuggestions(false);
                    }}
                  >
                    <Search size={16} />
                    <span>
                      Rechercher « {query.trim()} »
                      <small>Utiliser le texte saisi</small>
                    </span>
                  </button>
                  <div
                    className="suggestion-options"
                    role="group"
                    aria-label="Métiers ROME"
                  >
                    {suggestions.map((suggestion) => (
                      <button
                        type="button"
                        role="option"
                        aria-selected="false"
                        key={`${suggestion.code}-${suggestion.label}`}
                        onClick={() => {
                          analysisRequestRef.current?.abort();
                          setQuery(suggestion.label);
                          setShowSuggestions(false);
                        }}
                      >
                        <BriefcaseBusiness size={16} />
                        <span>
                          {suggestion.label}
                          <small>ROME {suggestion.code}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <button
              className="analyze-button"
              disabled={query.trim().length < 2}
            >
              {loading ? (
                <RefreshCw className="spin" size={19} />
              ) : (
                <Sparkles size={19} />
              )}
              {loading ? "Analyse en cours" : "Analyser"}
            </button>
          </form>
        </section>

        {error && (
          <div className="error-banner">
            <strong>Analyse interrompue</strong>
            <span>{error}</span>
            <button onClick={() => void runAnalysis()}>Réessayer</button>
          </div>
        )}
        {(analysis || loading) && (
          <section
            ref={resultsRef}
            className={`results ${loading ? "is-loading" : ""}`}
            aria-busy={loading}
          >
            {analysis && (
              <>
                <div className="results-head">
                  <div>
                    <div className="result-meta">
                      {analysis.cached ? (
                        <span className="cache-badge">Résultat en cache</span>
                      ) : (
                        <span className="mode-badge">Données en direct</span>
                      )}
                    </div>
                    <h2>Profil de compétences · {analysis.query}</h2>
                    <p>
                      Mis à jour le{" "}
                      {new Intl.DateTimeFormat("fr-FR", {
                        dateStyle: "long",
                        timeStyle: "short",
                      }).format(new Date(analysis.generated_at))}
                    </p>
                  </div>
                </div>
                <div className="kpi-grid">
                  <article className="kpi-card dark">
                    <div className="kpi-icon">
                      <BriefcaseBusiness size={20} />
                    </div>
                    <span>Offres analysées</span>
                    <strong>{analysis.total_offers}</strong>
                    <small>
                      {analysis.usable_offers} avec des compétences exploitables
                    </small>
                  </article>
                  <article className="kpi-card accent">
                    <div className="kpi-icon">
                      <BarChart3 size={20} />
                    </div>
                    <span>Compétence dominante</span>
                    <strong className="skill-name">
                      {topSkill?.name ?? "—"}
                    </strong>
                    <small>
                      {topSkill
                        ? `${topSkill.offer_count} offres · ${topSkill.percentage}%`
                        : "Aucune donnée"}
                    </small>
                  </article>
                  <article className="kpi-card coverage">
                    <div
                      className="coverage-ring"
                      style={
                        {
                          "--coverage": `${analysis.coverage_percentage * 3.6}deg`,
                        } as React.CSSProperties
                      }
                    >
                      <span>{analysis.coverage_percentage}%</span>
                    </div>
                    <div>
                      <span>Couverture des données</span>
                      <strong>
                        {analysis.coverage_percentage >= 75
                          ? "Très bonne"
                          : "À interpréter"}
                      </strong>
                      <small>Part des offres exploitables</small>
                    </div>
                  </article>
                </div>
                <div className="dashboard-grid">
                  <article className="panel chart-panel">
                    <div className="panel-head">
                      <div>
                        <span>Top 10</span>
                        <h3>Compétences les plus demandées</h3>
                      </div>
                      <small>% des offres analysées</small>
                    </div>
                    <div className="chart-wrap">
                      <Suspense
                        fallback={
                          <div className="chart-loading">
                            Préparation du graphique…
                          </div>
                        }
                      >
                        <SkillChart data={chartData} />
                      </Suspense>
                    </div>
                  </article>
                  <article className="panel education-panel">
                    <div className="panel-head">
                      <div>
                        <span>Formation</span>
                        <h3>Niveaux d’études cités</h3>
                      </div>
                    </div>
                    <div className="education-list">
                      {analysis.education_levels.length ? (
                        analysis.education_levels.map((item) => (
                          <div className="education-item" key={item.level}>
                            <div>
                              <strong>{item.level}</strong>
                              <span>{item.offer_count} offres</span>
                            </div>
                            <div className="progress">
                              <span
                                style={{
                                  width: `${Math.min(item.percentage, 100)}%`,
                                }}
                              />
                            </div>
                            <b>{item.percentage}%</b>
                          </div>
                        ))
                      ) : (
                        <p className="empty-copy">
                          Aucun niveau d’études explicite dans cet échantillon.
                        </p>
                      )}
                    </div>
                    <div className="method-note">
                      <Sparkles size={18} />
                      <p>
                        <strong>Analyse par Gemini</strong>Les descriptions et
                        les formations déclarées sont interprétées sans déduire
                        un diplôme depuis le métier.
                      </p>
                    </div>
                  </article>
                </div>
              </>
            )}
            {loading && (
              <div className="loading-overlay">
                <div className="loader-bars">
                  <span />
                  <span />
                  <span />
                </div>
                <strong>Lecture des offres et analyse des compétences…</strong>
              </div>
            )}
          </section>
        )}
      </main>
      <footer className="site-footer">
        <div className="footer-content">
          <div className="brand">
            <img
              className="brand-logo footer-logo"
              src="/SkillScope.svg"
              alt="SkillScope"
            />
          </div>
          <p className="footer-credit">
            Développé par{" "}
            <a
              href="https://hamza-kachmir.github.io/Portfolio/"
              target="_blank"
              rel="noreferrer"
            >
              Hamza Kachmir
            </a>
          </p>
          <p className="footer-note">
            Données officielles France Travail · Analyse indicative du marché
          </p>
        </div>
      </footer>
      {showMethod && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={() => setShowMethod(false)}
        >
          <section
            ref={methodModalRef}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="method-title"
            aria-describedby="method-description"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <button
              ref={methodCloseRef}
              className="modal-close"
              type="button"
              aria-label="Fermer"
              onClick={() => setShowMethod(false)}
            >
              <X />
            </button>
            <span className="modal-icon">
              <ShieldCheck />
            </span>
            <h2 id="method-title">Une méthode simple et vérifiable</h2>
            <p id="method-description">
              Les offres France Travail sont analysées par Gemini. L’IA extrait
              uniquement les compétences explicitement demandées, puis regroupe
              les variantes évidentes. Chaque compétence compte au maximum une
              fois par offre.
            </p>
            <ol>
              <li>
                <b>01</b>
                <span>
                  <strong>Échantillon officiel</strong>Jusqu’à 100 offres
                  actives correspondant au métier sont récupérées.
                </span>
              </li>
              <li>
                <b>02</b>
                <span>
                  <strong>Extraction intelligente</strong>Gemini identifie les
                  technologies et savoir-faire réellement demandés.
                </span>
              </li>
              <li>
                <b>03</b>
                <span>
                  <strong>Comptage par offre</strong>Chaque compétence compte au
                  maximum une fois dans une même offre.
                </span>
              </li>
              <li>
                <b>04</b>
                <span>
                  <strong>Transparence</strong>Le classement expose occurrences,
                  pourcentages et couverture.
                </span>
              </li>
            </ol>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
