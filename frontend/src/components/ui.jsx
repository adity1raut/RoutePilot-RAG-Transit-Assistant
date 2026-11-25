import { Bus, Check, ChevronDown, CircleAlert, Loader2, MapPin, Moon, Search, Snowflake, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { DAY_TYPES } from "../api";

export const cx = (...classes) => classes.filter(Boolean).join(" ");

// ------------------------------------------------------------------ route identity
const BADGE_STYLES = {
  Ordinary: "bg-blue-600 text-white",
  AC: "bg-teal-600 text-white",
  Night: "bg-violet-700 text-white",
};

const BADGE_SIZES = {
  sm: "h-5 min-w-[1.75rem] px-1.5 text-[11px]",
  md: "h-6 min-w-[2.25rem] px-2 text-xs",
  lg: "h-9 min-w-[3rem] px-2.5 text-base",
};

export function RouteBadge({ routeNo, busType = "Ordinary", size = "md", className = "" }) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-md font-bold tabular-nums tracking-tight",
        BADGE_STYLES[busType] || BADGE_STYLES.Ordinary,
        BADGE_SIZES[size],
        className,
      )}
      title={`Route ${routeNo} · ${busType} bus`}
    >
      {routeNo}
    </span>
  );
}

const BUS_TYPE_TAGS = {
  Ordinary: { icon: Bus, tone: "blue" },
  AC: { icon: Snowflake, tone: "teal" },
  Night: { icon: Moon, tone: "violet" },
};

export function BusTypeTag({ busType }) {
  const { icon: Icon, tone } = BUS_TYPE_TAGS[busType] || BUS_TYPE_TAGS.Ordinary;
  return (
    <Badge tone={tone}>
      <Icon className="h-3 w-3" aria-hidden />
      {busType}
    </Badge>
  );
}

const TONES = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  teal: "bg-teal-50 text-teal-700 ring-teal-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
};

export function Badge({ tone = "neutral", children, className = "" }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone], className)}>
      {children}
    </span>
  );
}

// ------------------------------------------------------------------ layout
export function Logo({ className = "h-9 w-9" }) {
  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-sm", className)}>
      <Bus className="h-[55%] w-[55%]" aria-hidden />
    </span>
  );
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ children, className = "", padded = true }) {
  return <div className={cx("rounded-2xl border border-slate-200/80 bg-white shadow-card", padded && "p-5", className)}>{children}</div>;
}

export function CardHeader({ icon: Icon, title, subtitle, action, className = "" }) {
  return (
    <div className={cx("flex items-start justify-between gap-3", className)}>
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
            <Icon className="h-[18px] w-[18px]" aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold leading-6 text-slate-900">{title}</h2>
          {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function Stat({ icon: Icon, label, value, hint }) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{value}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ form controls
export const inputClass =
  "h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 text-[15px] text-slate-900 shadow-sm transition " +
  "placeholder:text-slate-400 hover:border-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/15";

export function Field({ label, htmlFor, children, className = "" }) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </label>
      {children}
    </div>
  );
}

export function Select({ id, value, onChange, options, placeholder }) {
  return (
    <div className="relative">
      <select id={id} className={cx(inputClass, "appearance-none pr-10")} value={value} onChange={(e) => onChange(e.target.value)}>
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => {
          const { value: v, label } = typeof o === "string" ? { value: o, label: o } : o;
          return (
            <option key={v} value={v}>
              {label}
            </option>
          );
        })}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
    </div>
  );
}

export function Segmented({ value, onChange, options, label, className = "" }) {
  const items = options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  const onKeyDown = (e) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const next = (items.findIndex((o) => o.value === value) + step + items.length) % items.length;
    onChange(items[next].value);
    e.currentTarget.querySelectorAll("[role=radio]")[next]?.focus();
  };
  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cx("flex h-11 w-full gap-1 rounded-xl bg-slate-100 p-1", className)}
    >
      {items.map(({ value: v, label: text }) => {
        const active = v === value;
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(v)}
            className={cx(
              "min-w-0 flex-1 truncate rounded-lg px-2 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40",
              active ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200" : "text-slate-500 hover:text-slate-800",
            )}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

const DAY_LABELS = { Weekday: "Weekday", Saturday: "Saturday", "Sunday/Holiday": "Sun / Holiday" };

export function DaySelect({ value, onChange, label = "Day" }) {
  return (
    <Field label={label}>
      <Segmented value={value} onChange={onChange} label={label} options={DAY_TYPES.map((d) => ({ value: d, label: DAY_LABELS[d] }))} />
    </Field>
  );
}

/** Searchable stop picker (combobox): type to filter, arrow keys to move, Enter to choose. */
export function StopSelect({ label, value, onChange, stops, icon: Icon = MapPin, placeholder = "Search a stop" }) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listRef = useRef(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? stops.filter((s) => s.toLowerCase().includes(q)) : stops;
  }, [query, stops]);

  useEffect(() => {
    if (open) listRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const choose = (stop) => {
    onChange(stop);
    setQuery("");
    setOpen(false);
  };

  function onKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (matches[active]) choose(matches[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <Field label={label} htmlFor={id}>
      <div className="relative">
        <Icon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[active] ? `${id}-${active}` : undefined}
          autoComplete="off"
          placeholder={open && value ? value : placeholder}
          className={cx(inputClass, "pl-10 pr-10", value && !open && "font-medium")}
          value={open ? query : value}
          onFocus={() => {
            setOpen(true);
            setQuery("");
            setActive(Math.max(0, stops.indexOf(value)));
          }}
          onBlur={() => setOpen(false)}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {value && !open ? (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label={`Clear ${label}`}
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <Search className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-300" aria-hidden />
        )}
        {open && (
          <ul
            id={`${id}-list`}
            ref={listRef}
            role="listbox"
            className="absolute z-30 mt-1.5 max-h-64 w-full overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lift"
          >
            {matches.length === 0 ? (
              <li className="px-3 py-2 text-sm text-slate-500">
                {stops.length ? `No stop matches “${query}”` : "Stops are not loaded yet. Is the backend running?"}
              </li>
            ) : (
              matches.map((s, i) => (
                <li
                  key={s}
                  id={`${id}-${i}`}
                  role="option"
                  aria-selected={s === value}
                  onPointerDown={(e) => e.preventDefault()} // keep focus in the input
                  onClick={() => choose(s)}
                  onMouseEnter={() => setActive(i)}
                  className={cx(
                    "flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm",
                    i === active ? "bg-blue-50 text-blue-900" : "text-slate-700",
                  )}
                >
                  {s}
                  {s === value && <Check className="h-4 w-4 shrink-0 text-blue-600" aria-hidden />}
                </li>
              ))
            )}
          </ul>
        )}
      </div>
    </Field>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-blue-600 text-white shadow-sm hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none",
  secondary: "border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:text-slate-900 disabled:text-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400",
};

export function Button({ children, variant = "primary", size = "md", className = "", ...props }) {
  return (
    <button
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-xl font-semibold transition",
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-500/25 disabled:cursor-not-allowed",
        size === "sm" ? "h-9 px-3 text-sm" : "h-11 px-4 text-sm",
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ feedback
export function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
      <Loader2 className="h-4 w-4 animate-spin text-blue-600" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorNote({ message }) {
  if (!message) return null;
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Empty({ icon: Icon = Search, title, children, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      {title && <p className="mt-4 font-semibold text-slate-900">{title}</p>}
      {children && <p className="mt-1 max-w-sm text-sm text-slate-500">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
