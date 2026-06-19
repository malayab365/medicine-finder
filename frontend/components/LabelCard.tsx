import { LABEL_FIELDS, type Label } from "@/types";

export default function LabelCard({
  heading,
  rxcui,
  label,
  fallback,
}: {
  heading: string;
  rxcui: string | null;
  label: Label | null;
  fallback: string;
}) {
  if (!label) {
    return (
      <article className="mt-4 rounded-md border border-gray-200 bg-white p-5">
        <h2 className="text-lg font-semibold">{heading}</h2>
        <p className="mt-1 text-gray-700">{fallback}</p>
      </article>
    );
  }

  const fields = LABEL_FIELDS.filter(([key]) => label[key]);

  return (
    <article className="mt-4 rounded-md border border-gray-200 bg-white p-5">
      <h2 className="text-lg font-semibold">
        {heading}
        {rxcui ? <span className="ml-2 text-sm font-normal text-gray-500">(RxCUI {rxcui})</span> : null}
      </h2>
      {fields.map(([key, title]) => (
        <section key={key} className="mt-3">
          <h3 className="text-base font-semibold">{title}</h3>
          <p className="mt-1 whitespace-pre-wrap text-gray-800">{label[key]}</p>
        </section>
      ))}
    </article>
  );
}
