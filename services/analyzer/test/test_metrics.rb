# frozen_string_literal: true

require "test_helper"
require "analyzer/metrics"

class TestMetrics < Minitest::Test
  def analyse(source, path: "invoice.rb")
    Analyzer::Metrics.call(path: path, source: source)
  end

  def test_reports_the_path_it_was_given
    assert_equal "app/models/invoice.rb", analyse(CLEAN_RUBY, path: "app/models/invoice.rb")[:path]
  end

  def test_scores_clean_code_with_a_low_flog_average
    assert_operator analyse(CLEAN_RUBY)[:flog_average], :<, 10
  end

  def test_scores_tangled_code_with_a_high_flog_average
    assert_operator analyse(COMPLEX_RUBY)[:flog_average], :>, 20
  end

  def test_counts_reek_smells
    assert_operator analyse(COMPLEX_RUBY)[:smells], :>, analyse(CLEAN_RUBY)[:smells]
  end

  def test_names_the_smells_it_found
    types = analyse(COMPLEX_RUBY)[:smell_types]

    assert_includes types, "LongParameterList"
  end

  def test_smell_detail_carries_message_and_line
    detail = analyse(COMPLEX_RUBY)[:smell_details].first

    assert detail[:type], "expected a smell type"
    assert detail[:message], "expected a human-readable message"
    assert_kind_of Array, detail[:lines]
  end

  def test_unparseable_ruby_is_reported_rather_than_raising
    result = analyse("class Broken\n  def oops(\n")

    assert result[:error], "expected an error field for unparseable source"
  end
end
