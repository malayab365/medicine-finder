export function DisclaimerBanner({ text }: { text: string }) {
  return (
    <div className="my-4 rounded-md border border-yellow-300 bg-yellow-100 px-4 py-3 text-sm text-yellow-900">
      {text}
    </div>
  );
}

export function DisclaimerFooter({ text }: { text: string }) {
  return (
    <p className="mt-4 border-t border-gray-200 pt-3 text-sm text-gray-500">{text}</p>
  );
}

export function ErrorBox({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="my-4 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
      <strong>{title}</strong>
      {children ? <div className="mt-1">{children}</div> : null}
    </div>
  );
}
