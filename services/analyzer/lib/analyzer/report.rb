# frozen_string_literal: true

require "analyzer/metrics"

module Analyzer
  # Applies thresholds to measured files and produces the verdict.
  #
  # The definition of "clean" lives here, on the Ruby side, rather than in the
  # Python caller: the analyzer owns the policy, the caller reports the verdict
  # it is given.
  module Report
    # Measured against representative samples rather than picked by feel. A
    # clean file still scores one reek smell (IrresponsibleModule), so a
    # zero-smell gate would reject good code.
    DEFAULT_FLOG_AVERAGE = 20
    DEFAULT_SMELLS = 3

    module_function

    def call(files:, flog_average: DEFAULT_FLOG_AVERAGE, smells: DEFAULT_SMELLS)
      limits = { flog_average: flog_average, smells: smells }

      analysed = files.map do |f|
        metrics = Metrics.call(path: f["path"] || f[:path], source: f["source"] || f[:source])
        metrics.merge(violations: violations_for(metrics, limits))
      end

      {
        verdict: analysed.any? { |f| f[:violations].any? } ? "complex" : "clean",
        thresholds: limits,
        files: analysed
      }
    end

    def violations_for(metrics, limits)
      found = []

      if metrics[:error]
        found << { rule: "parse_error", actual: 0, limit: 0,
                   message: "file could not be parsed: #{metrics[:error]}" }
        return found
      end

      if metrics[:flog_average] > limits[:flog_average]
        found << { rule: "flog_average", actual: metrics[:flog_average],
                   limit: limits[:flog_average],
                   message: "average method complexity is #{metrics[:flog_average]} " \
                            "(limit #{limits[:flog_average]}); " \
                            "worst: #{describe_worst(metrics)}" }
      end

      if metrics[:smells] > limits[:smells]
        found << { rule: "smells", actual: metrics[:smells], limit: limits[:smells],
                   message: "#{metrics[:smells]} code smells (limit #{limits[:smells]}): " \
                            "#{metrics[:smell_types].join(', ')}" }
      end

      found
    end

    def describe_worst(metrics)
      worst = metrics[:worst_methods] || []
      return "n/a" if worst.empty?

      worst.map { |m| "#{m[:name]} (#{m[:score]})" }.join(", ")
    end
  end
end
