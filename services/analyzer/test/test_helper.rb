# frozen_string_literal: true

require "minitest/autorun"

CLEAN_RUBY = <<~RUBY_SRC
  # frozen_string_literal: true

  # Calculates invoice totals.
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
RUBY_SRC

COMPLEX_RUBY = <<~RUBY_SRC
  class InvoiceProcessor
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
          total += i[:amount]
          tax += i[:amount] * 0.05 unless flags.include?(:exempt)
        else
          total += i[:amount] if i[:amount]
        end
      end
      { total: total, tax: tax }
    end
  end
RUBY_SRC
