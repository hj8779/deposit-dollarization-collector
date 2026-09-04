import { useTranslation } from "react-i18next";
import type { CountrySummary } from "../lib/types";

interface Props {
  country: CountrySummary;
}

/** Shows the collector's source metadata (config/targets.json, synced into
 * country_metadata) below the chart: where the data comes from and any notes
 * the parser author left about quirks/limitations. */
export function SourceInfo({ country }: Props) {
  const { t } = useTranslation();
  const hasAnything = country.source_url || country.notes || country.adapter_notes;
  if (!hasAnything) return null;

  return (
    <div className="source-info">
      <h3>{t("sourceInfo.title")}</h3>
      <dl>
        {country.data_type && (
          <>
            <dt>{t("sourceInfo.type")}</dt>
            <dd>{country.data_type}</dd>
          </>
        )}
        {country.source_url && (
          <>
            <dt>{t("sourceInfo.url")}</dt>
            <dd>
              <a href={country.source_url} target="_blank" rel="noreferrer">
                {country.source_url}
              </a>
            </dd>
          </>
        )}
        {country.adapter_status && (
          <>
            <dt>{t("sourceInfo.status")}</dt>
            <dd>
              <span className={`badge status-${country.adapter_status}`}>
                {country.adapter_status}
              </span>
            </dd>
          </>
        )}
        {country.notes && (
          <>
            <dt>{t("sourceInfo.notes")}</dt>
            <dd>{country.notes}</dd>
          </>
        )}
        {country.adapter_notes && (
          <>
            <dt>{t("sourceInfo.adapterNotes")}</dt>
            <dd className="small">{country.adapter_notes}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
