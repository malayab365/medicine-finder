import NameSearch from "@/components/NameSearch";

export default function HomePage() {
  return (
    <div>
      <p className="mb-4 text-gray-600">
        Search a medicine by name to see its uses, dosage, warnings, side effects, and most-reported
        adverse events.
      </p>
      <NameSearch />
    </div>
  );
}
