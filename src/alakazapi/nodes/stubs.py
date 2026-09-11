"""Stub coder nodes for exercising the pipeline without Claude Code tokens.

These stand in for the real Claude Code node. They write genuine Ruby into the
repository rather than only reporting that they did, because the analyzer reads
files — a stub that returned a transcript alone would make the end-to-end test
theatre.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config import RunConfig
from ..state import PipelineState

# Scores flog ~1.6 / 1 reek smell: comfortably inside the default thresholds.
CLEAN_RUBY = '''# frozen_string_literal: true

# Calculates totals for an invoice.
class Invoice
  TAX_RATE = 0.13

  def initialize(line_items)
    @line_items = line_items
  end

  def subtotal
    @line_items.sum(&:amount)
  end

  def tax
    (subtotal * TAX_RATE).round(2)
  end

  def total
    subtotal + tax
  end
end
'''

# Scores flog ~51 / 9 reek smells: fails both default gates.
COMPLEX_RUBY = '''class InvoiceProcessor
  def process(items, opts = {}, mode = nil, flags = [])
    total = 0
    tax = 0
    items.each do |i|
      if i[:type] == "goods"
        if opts[:region] == "CA"
          if flags.include?(:exempt)
            total += i[:amount]
          else
            total += i[:amount]
            tax += i[:amount] * 0.13
          end
        elsif opts[:region] == "US"
          if mode == :wholesale
            total += i[:amount] * 0.9
            tax += i[:amount] * 0.07 unless flags.include?(:exempt)
          else
            total += i[:amount]
            tax += i[:amount] * 0.07 unless flags.include?(:exempt)
          end
        else
          total += i[:amount]
        end
      elsif i[:type] == "service"
        if opts[:region] == "CA"
          total += i[:amount]
          tax += i[:amount] * 0.05 unless flags.include?(:exempt)
        else
          total += i[:amount]
        end
      else
        total += i[:amount] if i[:amount]
      end
    end
    { total: total, tax: tax, grand: total + tax }
  end
end
'''

# The tangled version above, refactored. Scores inside both default gates, so a
# run using the improving stub converges instead of exhausting its iterations.
REFACTORED_RUBY = """# frozen_string_literal: true

# Calculates invoice totals for a single region.
class InvoiceProcessor
  RATES = { "CA" => 0.13, "US" => 0.07 }.freeze

  def initialize(region:, exempt: false)
    @region = region
    @exempt = exempt
  end

  def process(items)
    subtotal = items.sum { |item| item.fetch(:amount, 0) }
    tax = tax_for(subtotal)

    { total: subtotal, tax: tax, grand: subtotal + tax }
  end

  private

  def tax_for(subtotal)
    return 0 if @exempt

    (subtotal * RATES.fetch(@region, 0)).round(2)
  end
end
"""


def _write(
    state: PipelineState,
    config: RunConfig,
    filename: str,
    source: str,
    summary: str,
    emit: Callable[[dict], None] | None,
) -> dict:
    target = Path(config.repo) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")

    if emit is not None:
        emit({"type": "text", "text": summary})
        emit({"type": "tool", "name": "Write", "input": {"file_path": str(target)}})

    return {
        "transcript": summary,
        "tool_calls": ["Write"],
        "session_id": state.get("session_id") or "stub-session",
        "cost_usd": state.get("cost_usd", 0.0),
        "iteration": state.get("iteration", 0) + 1,
        "error": None,
    }


async def clean_code_node(
    state: PipelineState,
    config: RunConfig,
    emit: Callable[[dict], None] | None = None,
    **_ignored,
) -> dict:
    """Produce well-factored Ruby that passes the analysis gate."""
    return _write(
        state, config, "invoice.rb", CLEAN_RUBY,
        "Wrote invoice.rb with a small Invoice class: subtotal, tax, and total.",
        emit,
    )


async def complex_code_node(
    state: PipelineState,
    config: RunConfig,
    emit: Callable[[dict], None] | None = None,
    **_ignored,
) -> dict:
    """Produce tangled Ruby that fails the analysis gate.

    It deliberately ignores feedback and rewrites the same file every pass, so
    the run loops until max_iterations and the return into `code` is observable.
    """
    return _write(
        state, config, "invoice_processor.rb", COMPLEX_RUBY,
        "Wrote invoice_processor.rb with a process method handling all the tax cases.",
        emit,
    )


async def improving_code_node(
    state: PipelineState,
    config: RunConfig,
    emit: Callable[[dict], None] | None = None,
    **_ignored,
) -> dict:
    """Produce tangled Ruby first, then refactor it once analysis pushes back.

    This is the convergence case: the first pass fails the gate, the second
    replaces the same file with a clean version, and the run reaches the
    reviewer instead of exhausting its iterations.
    """
    first_pass = state.get("iteration", 0) == 0
    source = COMPLEX_RUBY if first_pass else REFACTORED_RUBY
    summary = (
        "Wrote invoice_processor.rb with a process method handling all the tax cases."
        if first_pass
        else "Refactored invoice_processor.rb: extracted tax_for, replaced the nested "
        "conditionals with a rates table."
    )

    return _write(state, config, "invoice_processor.rb", source, summary, emit)


STUBS = {
    "clean": clean_code_node,
    "complex": complex_code_node,
    "improving": improving_code_node,
}


def stub_for(name: str):
    try:
        return STUBS[name]
    except KeyError:
        raise ValueError(f"unknown stub {name!r}; choose one of {sorted(STUBS)}") from None
