type LoginSheetProps = {
  onContinue: () => void;
};

function LoginSheet({ onContinue }: LoginSheetProps) {
  return (
    <div className="mx-4 mb-4 rounded-2xl border border-white/[0.08] bg-[#111] p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mb-1 text-[15px] font-medium text-white">Start planning</p>
          <p className="text-[12px] text-white/35">Sign in to save, book &amp; discover</p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            className="flex items-center gap-2 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-xs text-white/70"
          >
            <span className="h-[14px] w-[14px] rounded-full bg-gradient-to-br from-blue-500 via-red-500 to-yellow-400" />
            Google
          </button>

          <button
            type="button"
            onClick={onContinue}
            className="rounded-full bg-[#f97316] px-4 py-2 text-xs font-medium text-white"
          >
            Continue →
          </button>
        </div>
      </div>
    </div>
  );
}

export default LoginSheet;
