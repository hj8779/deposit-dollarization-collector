import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DbSummaryTable } from "./components/DbSummaryTable";
import { ChartForm } from "./components/ChartForm";
import { FrequencyCoverageBar } from "./components/FrequencyCoverageBar";
import { fetchCountrySummaries } from "./lib/db";
import { useEffectQuery } from "./lib/useEffectQuery";
import "./App.css";

function App() {
  const { t, i18n } = useTranslation();
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  // Fetched once here (not inside ChartForm) so the country <select> can be
  // populated even before/independent of which row the user clicked in the table.
  const { data: countries } = useEffectQuery(fetchCountrySummaries, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>{t("app.title")}</h1>
        <div className="lang-toggle" role="group" aria-label="Language">
          <button
            type="button"
            className={i18n.language === "ko" ? "active" : ""}
            onClick={() => i18n.changeLanguage("ko")}
          >
            {t("app.langToggleKo")}
          </button>
          <button
            type="button"
            className={i18n.language === "en" ? "active" : ""}
            onClick={() => i18n.changeLanguage("en")}
          >
            {t("app.langToggleEn")}
          </button>
        </div>
      </header>

      <FrequencyCoverageBar />

      <main className="app-grid">
        <DbSummaryTable selectedCountry={selectedCountry} onSelectCountry={setSelectedCountry} />
        <ChartForm
          countries={countries ?? []}
          selectedCountry={selectedCountry}
          onSelectCountry={setSelectedCountry}
        />
      </main>
    </div>
  );
}

export default App;
