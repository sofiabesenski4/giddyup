# frozen_string_literal: true

require "test_helper"
require "rack/test"
require "json"
require "analyzer/app"

class TestApp < Minitest::Test
  include Rack::Test::Methods

  def app
    Analyzer::App.new
  end

  def body
    JSON.parse(last_response.body, symbolize_names: true)
  end

  def analyze(payload)
    post "/analyze", JSON.dump(payload), { "CONTENT_TYPE" => "application/json" }
  end

  def test_health_reports_ok_with_the_ruby_version
    get "/health"

    assert_equal 200, last_response.status
    assert_equal "ok", body[:status]
    assert_equal RUBY_VERSION, body[:ruby]
  end

  def test_analyze_returns_a_clean_verdict_for_clean_ruby
    analyze(files: [{ path: "invoice.rb", source: CLEAN_RUBY }])

    assert_equal 200, last_response.status
    assert_equal "clean", body[:verdict]
  end

  def test_analyze_returns_a_complex_verdict_with_violations
    analyze(files: [{ path: "processor.rb", source: COMPLEX_RUBY }])

    assert_equal "complex", body[:verdict]
    refute_empty body[:files].first[:violations]
  end

  def test_analyze_accepts_threshold_overrides
    analyze(files: [{ path: "invoice.rb", source: CLEAN_RUBY }],
            thresholds: { flog_average: 0.1, smells: 0 })

    assert_equal "complex", body[:verdict]
  end

  def test_malformed_json_is_a_400_not_a_crash
    post "/analyze", "{not json", { "CONTENT_TYPE" => "application/json" }

    assert_equal 400, last_response.status
    assert body[:error]
  end

  def test_missing_files_key_is_a_400
    analyze(something_else: true)

    assert_equal 400, last_response.status
  end

  def test_unknown_path_is_a_404
    get "/nope"

    assert_equal 404, last_response.status
  end

  def test_responses_are_json
    get "/health"

    assert_match "application/json", last_response.headers["content-type"]
  end
end
