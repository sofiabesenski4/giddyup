# frozen_string_literal: true

require "json"
require "rack"
require "analyzer/report"

module Analyzer
  # The HTTP boundary. Two endpoints, so Rack directly rather than Sinatra.
  class App
    JSON_HEADERS = { "content-type" => "application/json" }.freeze

    def call(env)
      request = Rack::Request.new(env)

      case [request.request_method, request.path_info]
      when %w[GET /health] then json(200, health)
      when %w[POST /analyze] then analyze(request)
      else json(404, error: "no such endpoint: #{request.request_method} #{request.path_info}")
      end
    end

    private

    def health
      { status: "ok", ruby: RUBY_VERSION, analyzers: %w[flog reek] }
    end

    def analyze(request)
      payload = parse(request)
      files = payload[:files]
      return json(400, error: "expected a 'files' array") unless files.is_a?(Array)

      thresholds = payload[:thresholds] || {}
      json(200, Report.call(files: files.map { |f| stringify(f) }, **threshold_options(thresholds)))
    rescue JSON::ParserError => e
      json(400, error: "malformed JSON: #{e.message}")
    end

    def parse(request)
      request.body.rewind
      JSON.parse(request.body.read, symbolize_names: true)
    end

    def threshold_options(thresholds)
      opts = {}
      opts[:flog_average] = thresholds[:flog_average] if thresholds[:flog_average]
      opts[:smells] = thresholds[:smells] if thresholds[:smells]
      opts
    end

    def stringify(file)
      { "path" => file[:path] || file["path"], "source" => file[:source] || file["source"] }
    end

    def json(status, payload)
      [status, JSON_HEADERS.dup, [JSON.dump(payload)]]
    end
  end
end
