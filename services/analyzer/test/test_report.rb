# frozen_string_literal: true

require "test_helper"
require "analyzer/report"

class TestReport < Minitest::Test
  def report(files, **opts)
    Analyzer::Report.call(files: files, **opts)
  end

  def file(path, source)
    { "path" => path, "source" => source }
  end

  def test_clean_ruby_is_reported_clean
    result = report([file("invoice.rb", CLEAN_RUBY)])

    assert_equal "clean", result[:verdict]
    assert_empty result[:files].first[:violations]
  end

  def test_tangled_ruby_is_reported_complex
    result = report([file("processor.rb", COMPLEX_RUBY)])

    assert_equal "complex", result[:verdict]
    refute_empty result[:files].first[:violations]
  end

  def test_a_violation_names_the_rule_the_actual_value_and_the_limit
    violation = report([file("processor.rb", COMPLEX_RUBY)])[:files].first[:violations]
                .find { |v| v[:rule] == "flog_average" }

    assert violation, "expected a flog_average violation"
    assert_operator violation[:actual], :>, violation[:limit]
    assert_match(/complexity/i, violation[:message])
  end

  def test_one_complex_file_makes_the_whole_run_complex
    result = report([file("ok.rb", CLEAN_RUBY), file("bad.rb", COMPLEX_RUBY)])

    assert_equal "complex", result[:verdict]
  end

  def test_thresholds_are_configurable
    strict = report([file("invoice.rb", CLEAN_RUBY)], flog_average: 0.1, smells: 0)

    assert_equal "complex", strict[:verdict], "a strict gate should reject even clean code"
  end

  def test_an_empty_file_list_is_clean_rather_than_an_error
    assert_equal "clean", report([])[:verdict]
  end

  def test_unparseable_ruby_counts_as_a_violation
    result = report([file("broken.rb", "class Broken\n  def oops(\n")])

    assert_equal "complex", result[:verdict]
    assert(result[:files].first[:violations].any? { |v| v[:rule] == "parse_error" })
  end

  def test_reports_the_thresholds_it_applied
    assert_equal 20, report([])[:thresholds][:flog_average]
  end
end
