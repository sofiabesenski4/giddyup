# frozen_string_literal: true

require "flog"
require "reek"

module Analyzer
  # Measures one Ruby source file using flog and reek as libraries.
  #
  # Everything here works on a source string rather than a path: the service
  # receives file contents over HTTP, so it never assumes a shared filesystem.
  module Metrics
    module_function

    def call(path:, source:)
      { path: path }.merge(flog(source, path)).merge(reek(source))
    rescue StandardError, SyntaxError => e
      # A coding agent mid-revision will hand us unparseable Ruby sooner or
      # later. That is a finding to report, not a reason to fail the request.
      { path: path, error: "#{e.class}: #{e.message}", flog_total: 0.0,
        flog_average: 0.0, smells: 0, smell_types: [], smell_details: [] }
    end

    def flog(source, path)
      flogger = Flog.new
      flogger.flog_ruby!(source, path)
      flogger.calculate_total_scores

      {
        flog_total: flogger.total_score.to_f.round(2),
        flog_average: flogger.average.to_f.round(2),
        worst_methods: flogger.totals.sort_by { |_, score| -score }.first(3)
                               .map { |name, score| { name: name, score: score.round(2) } }
      }
    end

    def reek(source)
      smells = Reek::Examiner.new(source).smells

      {
        smells: smells.size,
        smell_types: smells.map { |s| s.smell_type.to_s }.uniq.sort,
        smell_details: smells.map do |s|
          { type: s.smell_type.to_s, message: s.message,
            context: s.context.to_s, lines: s.lines }
        end
      }
    end
  end
end
