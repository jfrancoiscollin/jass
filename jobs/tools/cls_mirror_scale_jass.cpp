// SPDX-License-Identifier: AGPL-3.0-or-later
// CLS-D mirror-scale deep Jass parent-root reference.
// Reuses the proven depth-growth root profiler implementation, but fixes the
// requested node cap prospectively to the historical DEEP512 Jass1M budget.

#define main cls_depth_growth_jass_original_main_disabled
#include "cls_depth_growth_jass.cpp"
#undef main

int main(int argc, char** argv) {
    try {
        static_assert(std::endian::native == std::endian::little);
        if (argc != 7) {
            std::cerr << "usage: cls_mirror_scale_jass <parents.jnnw> <root_ids.txt> "
                         "<output.tsv> <report.json> <curriculum.pjtw> <egdb_dir>\n";
            return 2;
        }
        if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_T3_F6_MODEL") != nullptr
            || std::getenv("JASS_SEARCH_PARAMS") != nullptr) {
            throw std::runtime_error("forbidden runtime policy/model override");
        }
        constexpr std::uint64_t BUDGET = 1'000'000;
        const std::string parents_path = argv[1];
        const auto ids = load_ids(argv[2]);
        const std::string output_path = argv[3];
        const std::string report_path = argv[4];
        const std::string curriculum_path = argv[5];
        const std::string egdb_dir = argv[6];

        std::string error;
        auto curriculum = load_eval_network(curriculum_path, &error);
        if (!curriculum) throw std::runtime_error("cannot load CURRICULUM: " + error);
        if (!jass::egdb::init(egdb_dir, EGDB_CACHE_MB) || !jass::egdb::available())
            throw std::runtime_error("required real EGDB unavailable");

        std::ifstream in(parents_path, std::ios::binary);
        if (!in) throw std::runtime_error("cannot open parents.jnnw");
        std::array<char, 8> header{};
        if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
            || std::memcmp(header.data(), "JNNW", 4) != 0)
            throw std::runtime_error("bad parents JNNW header");
        const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
        for (const auto id : ids) if (id >= declared) throw std::runtime_error("root id outside parent corpus");

        std::ofstream out(output_path);
        if (!out) throw std::runtime_error("cannot open CLS mirror Jass output");
        out << "root_id\tbudget\tnodes_observed\tcompleted_nominal_depth\teffective_depth\t"
               "bestmove_canonical\tscore_cp\twall_us\tnps\tbranching\tforced_capture_at_root\t"
               "max_capture_len\tpieces\tstm\tqnodes\teval_calls\ttt_probes\ttt_hits\tcutoffs\t"
               "first_move_cutoffs\tpvs_researches\tmoves_searched\n";

        std::uint64_t searches = 0, nodes = 0, elapsed_us = 0;
        DiskRow row{};
        for (std::uint32_t idx = 0; idx < declared; ++idx) {
            if (!read_row(in, row)) throw std::runtime_error("truncated parents JNNW");
            if (!ids.count(idx)) continue;
            if (!valid_row(row) || row.score != 0 || row.wdl != 0)
                throw std::runtime_error("invalid or labelled CLS mirror parent row");
            const auto root = position_from_row(row);
            const auto shape = root_shape(root);
            if (shape.branching < 2 || shape.branching > 16)
                throw std::runtime_error("CLS mirror root branching outside frozen support");
            const int pieces = std::popcount(row.wm | row.wk | row.bm | row.bk);
            const auto obs = run_one(root, curriculum.get(), BUDGET);
            const auto& r = obs.result;
            const double nps = obs.elapsed_us == 0 ? 0.0
                : static_cast<double>(r.nodes) * 1'000'000.0 / static_cast<double>(obs.elapsed_us);
            out << idx << '\t' << BUDGET << '\t' << r.nodes << '\t' << r.completed_depth
                << '\t' << r.effective_depth << '\t' << canonical_move(r.best_move)
                << '\t' << r.score << '\t' << obs.elapsed_us << '\t' << nps
                << '\t' << shape.branching << '\t' << (shape.forced_capture ? 1 : 0)
                << '\t' << shape.max_capture_len << '\t' << pieces << '\t'
                << static_cast<int>(row.stm) << '\t' << r.qnodes << '\t' << r.eval_calls
                << '\t' << r.tt_probes << '\t' << r.tt_hits << '\t' << r.cutoffs
                << '\t' << r.first_move_cutoffs << '\t' << r.pvs_researches
                << '\t' << r.moves_searched << '\n';
            ++searches; nodes += r.nodes; elapsed_us += obs.elapsed_us;
        }
        if (in.read(reinterpret_cast<char*>(&row), 1)) throw std::runtime_error("trailing parent bytes");
        if (searches != ids.size()) throw std::runtime_error("CLS mirror search cardinality drift");
        out.close();

        std::ofstream report(report_path);
        if (!report) throw std::runtime_error("cannot write CLS mirror Jass report");
        report << "{\n"
               << "  \"schema\": \"jass.cls_mirror_scale_jass.v1\",\n"
               << "  \"diagnostic_only\": true,\n"
               << "  \"roots\": " << ids.size() << ",\n"
               << "  \"budget_nodes\": " << BUDGET << ",\n"
               << "  \"searches\": " << searches << ",\n"
               << "  \"nodes\": " << nodes << ",\n"
               << "  \"elapsed_us\": " << elapsed_us << ",\n"
               << "  \"tt_mb\": " << TT_MB << ",\n"
               << "  \"threads\": 1,\n"
               << "  \"book_enabled\": false,\n"
               << "  \"node_limit_mode\": \"exact\",\n"
               << "  \"fresh_engine_per_root\": true,\n"
               << "  \"labels_read\": 0,\n"
               << "  \"fits\": 0,\n"
               << "  \"strength_games\": 0,\n"
               << "  \"promotion_authorized\": false\n"
               << "}\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "CLS mirror Jass profiler error: " << exc.what() << '\n';
        return 3;
    }
}
