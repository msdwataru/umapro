export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      backtest_bets: {
        Row: {
          backtest_run_id: number
          bet_type_id: number
          created_at: string
          edge_value: number | null
          id: number
          is_hit: boolean
          payout_amount: number
          prediction_value: number | null
          race_entry_id: number | null
          race_id: number
          selection_key: string
          stake_amount: number
        }
        Insert: {
          backtest_run_id: number
          bet_type_id: number
          created_at?: string
          edge_value?: number | null
          id?: never
          is_hit: boolean
          payout_amount: number
          prediction_value?: number | null
          race_entry_id?: number | null
          race_id: number
          selection_key: string
          stake_amount: number
        }
        Update: {
          backtest_run_id?: number
          bet_type_id?: number
          created_at?: string
          edge_value?: number | null
          id?: never
          is_hit?: boolean
          payout_amount?: number
          prediction_value?: number | null
          race_entry_id?: number | null
          race_id?: number
          selection_key?: string
          stake_amount?: number
        }
        Relationships: [
          {
            foreignKeyName: "backtest_bets_backtest_run_id_fkey"
            columns: ["backtest_run_id"]
            isOneToOne: false
            referencedRelation: "backtest_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "backtest_bets_bet_type_id_fkey"
            columns: ["bet_type_id"]
            isOneToOne: false
            referencedRelation: "bet_types"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "backtest_bets_race_entry_id_fkey"
            columns: ["race_entry_id"]
            isOneToOne: false
            referencedRelation: "race_entries"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "backtest_bets_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: false
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
        ]
      }
      backtest_results: {
        Row: {
          avg_odds: number | null
          backtest_run_id: number
          bet_count: number
          bet_type_id: number
          created_at: string
          hit_count: number
          hit_rate: number
          id: number
          max_drawdown: number | null
          payout_amount: number
          race_count: number
          roi: number
          stake_amount: number
        }
        Insert: {
          avg_odds?: number | null
          backtest_run_id: number
          bet_count: number
          bet_type_id: number
          created_at?: string
          hit_count: number
          hit_rate: number
          id?: never
          max_drawdown?: number | null
          payout_amount: number
          race_count: number
          roi: number
          stake_amount: number
        }
        Update: {
          avg_odds?: number | null
          backtest_run_id?: number
          bet_count?: number
          bet_type_id?: number
          created_at?: string
          hit_count?: number
          hit_rate?: number
          id?: never
          max_drawdown?: number | null
          payout_amount?: number
          race_count?: number
          roi?: number
          stake_amount?: number
        }
        Relationships: [
          {
            foreignKeyName: "backtest_results_backtest_run_id_fkey"
            columns: ["backtest_run_id"]
            isOneToOne: false
            referencedRelation: "backtest_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "backtest_results_bet_type_id_fkey"
            columns: ["bet_type_id"]
            isOneToOne: false
            referencedRelation: "bet_types"
            referencedColumns: ["id"]
          },
        ]
      }
      backtest_runs: {
        Row: {
          created_at: string
          error_message: string | null
          finished_at: string | null
          id: number
          parameters_json: Json
          run_name: string | null
          started_at: string | null
          status: string
          user_id: string
        }
        Insert: {
          created_at?: string
          error_message?: string | null
          finished_at?: string | null
          id?: never
          parameters_json: Json
          run_name?: string | null
          started_at?: string | null
          status?: string
          user_id: string
        }
        Update: {
          created_at?: string
          error_message?: string | null
          finished_at?: string | null
          id?: never
          parameters_json?: Json
          run_name?: string | null
          started_at?: string | null
          status?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "backtest_runs_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "user_profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      bet_types: {
        Row: {
          code: string
          created_at: string
          id: number
          is_mvp_target: boolean
          name: string
          updated_at: string
        }
        Insert: {
          code: string
          created_at?: string
          id?: never
          is_mvp_target?: boolean
          name: string
          updated_at?: string
        }
        Update: {
          code?: string
          created_at?: string
          id?: never
          is_mvp_target?: boolean
          name?: string
          updated_at?: string
        }
        Relationships: []
      }
      entry_results: {
        Row: {
          abnormal_result_code: string | null
          created_at: string
          dead_heat_flag: boolean
          final_corner_position: number | null
          finish_position: number | null
          finish_time: string | null
          id: number
          last3f: number | null
          margin_text: string | null
          passing_order_text: string | null
          popularity_final: number | null
          prize_money: number | null
          race_entry_id: number
          updated_at: string
        }
        Insert: {
          abnormal_result_code?: string | null
          created_at?: string
          dead_heat_flag?: boolean
          final_corner_position?: number | null
          finish_position?: number | null
          finish_time?: string | null
          id?: never
          last3f?: number | null
          margin_text?: string | null
          passing_order_text?: string | null
          popularity_final?: number | null
          prize_money?: number | null
          race_entry_id: number
          updated_at?: string
        }
        Update: {
          abnormal_result_code?: string | null
          created_at?: string
          dead_heat_flag?: boolean
          final_corner_position?: number | null
          finish_position?: number | null
          finish_time?: string | null
          id?: never
          last3f?: number | null
          margin_text?: string | null
          passing_order_text?: string | null
          popularity_final?: number | null
          prize_money?: number | null
          race_entry_id?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "entry_results_race_entry_id_fkey"
            columns: ["race_entry_id"]
            isOneToOne: true
            referencedRelation: "race_entries"
            referencedColumns: ["id"]
          },
        ]
      }
      favorites: {
        Row: {
          created_at: string
          favorite_type: string
          horse_id: number | null
          id: number
          race_id: number | null
          user_id: string
        }
        Insert: {
          created_at?: string
          favorite_type: string
          horse_id?: number | null
          id?: never
          race_id?: number | null
          user_id: string
        }
        Update: {
          created_at?: string
          favorite_type?: string
          horse_id?: number | null
          id?: never
          race_id?: number | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "favorites_horse_id_fkey"
            columns: ["horse_id"]
            isOneToOne: false
            referencedRelation: "horses"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "favorites_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: false
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "favorites_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "user_profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      feature_sets: {
        Row: {
          created_at: string
          description: string | null
          feature_schema_json: Json | null
          feature_set_name: string
          id: number
          is_active: boolean
          training_cutoff_rule: string | null
          updated_at: string
          version: string
        }
        Insert: {
          created_at?: string
          description?: string | null
          feature_schema_json?: Json | null
          feature_set_name: string
          id?: never
          is_active?: boolean
          training_cutoff_rule?: string | null
          updated_at?: string
          version: string
        }
        Update: {
          created_at?: string
          description?: string | null
          feature_schema_json?: Json | null
          feature_set_name?: string
          id?: never
          is_active?: boolean
          training_cutoff_rule?: string | null
          updated_at?: string
          version?: string
        }
        Relationships: []
      }
      horses: {
        Row: {
          birth_date: string | null
          breeder_name: string | null
          created_at: string
          dam_name: string | null
          external_horse_code: string
          id: number
          name: string
          owner_name: string | null
          retired_at: string | null
          sex: string | null
          sire_name: string | null
          updated_at: string
        }
        Insert: {
          birth_date?: string | null
          breeder_name?: string | null
          created_at?: string
          dam_name?: string | null
          external_horse_code: string
          id?: never
          name: string
          owner_name?: string | null
          retired_at?: string | null
          sex?: string | null
          sire_name?: string | null
          updated_at?: string
        }
        Update: {
          birth_date?: string | null
          breeder_name?: string | null
          created_at?: string
          dam_name?: string | null
          external_horse_code?: string
          id?: never
          name?: string
          owner_name?: string | null
          retired_at?: string | null
          sex?: string | null
          sire_name?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      job_runs: {
        Row: {
          created_at: string
          error_summary: string | null
          finished_at: string | null
          id: number
          job_name: string
          job_type: string
          records_processed: number | null
          started_at: string | null
          status: string
          target_date: string | null
        }
        Insert: {
          created_at?: string
          error_summary?: string | null
          finished_at?: string | null
          id?: never
          job_name: string
          job_type: string
          records_processed?: number | null
          started_at?: string | null
          status?: string
          target_date?: string | null
        }
        Update: {
          created_at?: string
          error_summary?: string | null
          finished_at?: string | null
          id?: never
          job_name?: string
          job_type?: string
          records_processed?: number | null
          started_at?: string | null
          status?: string
          target_date?: string | null
        }
        Relationships: []
      }
      jockeys: {
        Row: {
          affiliation: string | null
          created_at: string
          external_jockey_code: string
          id: number
          name: string
          updated_at: string
        }
        Insert: {
          affiliation?: string | null
          created_at?: string
          external_jockey_code: string
          id?: never
          name: string
          updated_at?: string
        }
        Update: {
          affiliation?: string | null
          created_at?: string
          external_jockey_code?: string
          id?: never
          name?: string
          updated_at?: string
        }
        Relationships: []
      }
      model_predictions: {
        Row: {
          created_at: string
          edge_value: number | null
          feature_set_id: number
          id: number
          implied_probability: number | null
          model_version_id: number
          predicted_at: string
          predicted_value: number
          prediction_rank: number | null
          prediction_target: string
          race_entry_id: number
          source_odds_snapshot_at: string | null
        }
        Insert: {
          created_at?: string
          edge_value?: number | null
          feature_set_id: number
          id?: never
          implied_probability?: number | null
          model_version_id: number
          predicted_at: string
          predicted_value: number
          prediction_rank?: number | null
          prediction_target: string
          race_entry_id: number
          source_odds_snapshot_at?: string | null
        }
        Update: {
          created_at?: string
          edge_value?: number | null
          feature_set_id?: number
          id?: never
          implied_probability?: number | null
          model_version_id?: number
          predicted_at?: string
          predicted_value?: number
          prediction_rank?: number | null
          prediction_target?: string
          race_entry_id?: number
          source_odds_snapshot_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "model_predictions_feature_set_id_fkey"
            columns: ["feature_set_id"]
            isOneToOne: false
            referencedRelation: "feature_sets"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "model_predictions_model_version_id_fkey"
            columns: ["model_version_id"]
            isOneToOne: false
            referencedRelation: "model_versions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "model_predictions_race_entry_id_fkey"
            columns: ["race_entry_id"]
            isOneToOne: false
            referencedRelation: "race_entries"
            referencedColumns: ["id"]
          },
        ]
      }
      model_versions: {
        Row: {
          artifact_path: string | null
          created_at: string
          deployed_at: string | null
          feature_set_id: number
          id: number
          is_production: boolean
          metrics_json: Json | null
          model_name: string
          model_type: string
          training_period_end: string | null
          training_period_start: string | null
          updated_at: string
          version: string
        }
        Insert: {
          artifact_path?: string | null
          created_at?: string
          deployed_at?: string | null
          feature_set_id: number
          id?: never
          is_production?: boolean
          metrics_json?: Json | null
          model_name: string
          model_type: string
          training_period_end?: string | null
          training_period_start?: string | null
          updated_at?: string
          version: string
        }
        Update: {
          artifact_path?: string | null
          created_at?: string
          deployed_at?: string | null
          feature_set_id?: number
          id?: never
          is_production?: boolean
          metrics_json?: Json | null
          model_name?: string
          model_type?: string
          training_period_end?: string | null
          training_period_start?: string | null
          updated_at?: string
          version?: string
        }
        Relationships: [
          {
            foreignKeyName: "model_versions_feature_set_id_fkey"
            columns: ["feature_set_id"]
            isOneToOne: false
            referencedRelation: "feature_sets"
            referencedColumns: ["id"]
          },
        ]
      }
      odds_snapshots: {
        Row: {
          created_at: string
          id: number
          place_odds_max: number | null
          place_odds_min: number | null
          popularity: number | null
          race_entry_id: number
          snapshot_at: string
          source_status: string | null
          win_odds: number | null
        }
        Insert: {
          created_at?: string
          id?: never
          place_odds_max?: number | null
          place_odds_min?: number | null
          popularity?: number | null
          race_entry_id: number
          snapshot_at: string
          source_status?: string | null
          win_odds?: number | null
        }
        Update: {
          created_at?: string
          id?: never
          place_odds_max?: number | null
          place_odds_min?: number | null
          popularity?: number | null
          race_entry_id?: number
          snapshot_at?: string
          source_status?: string | null
          win_odds?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "odds_snapshots_race_entry_id_fkey"
            columns: ["race_entry_id"]
            isOneToOne: false
            referencedRelation: "race_entries"
            referencedColumns: ["id"]
          },
        ]
      }
      payouts: {
        Row: {
          bet_type_id: number
          combination_key: string
          created_at: string
          id: number
          payout_amount: number
          popularity: number | null
          race_id: number
        }
        Insert: {
          bet_type_id: number
          combination_key: string
          created_at?: string
          id?: never
          payout_amount: number
          popularity?: number | null
          race_id: number
        }
        Update: {
          bet_type_id?: number
          combination_key?: string
          created_at?: string
          id?: never
          payout_amount?: number
          popularity?: number | null
          race_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "payouts_bet_type_id_fkey"
            columns: ["bet_type_id"]
            isOneToOne: false
            referencedRelation: "bet_types"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "payouts_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: false
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
        ]
      }
      prediction_reasons: {
        Row: {
          body: string
          created_at: string
          display_order: number
          id: number
          model_prediction_id: number
          reason_type: string
          score: number | null
          title: string
        }
        Insert: {
          body: string
          created_at?: string
          display_order: number
          id?: never
          model_prediction_id: number
          reason_type: string
          score?: number | null
          title: string
        }
        Update: {
          body?: string
          created_at?: string
          display_order?: number
          id?: never
          model_prediction_id?: number
          reason_type?: string
          score?: number | null
          title?: string
        }
        Relationships: [
          {
            foreignKeyName: "prediction_reasons_model_prediction_id_fkey"
            columns: ["model_prediction_id"]
            isOneToOne: false
            referencedRelation: "model_predictions"
            referencedColumns: ["id"]
          },
        ]
      }
      race_entries: {
        Row: {
          blinkers_flag: boolean | null
          bracket_number: number | null
          carried_weight: number | null
          created_at: string
          declared_weight_diff_kg: number | null
          declared_weight_kg: number | null
          horse_id: number
          horse_number: number
          id: number
          jockey_id: number | null
          latest_place_odds_max: number | null
          latest_place_odds_min: number | null
          latest_win_odds: number | null
          morning_line_popularity: number | null
          race_id: number
          scratch_flag: boolean
          sex_age: string | null
          trainer_id: number | null
          updated_at: string
        }
        Insert: {
          blinkers_flag?: boolean | null
          bracket_number?: number | null
          carried_weight?: number | null
          created_at?: string
          declared_weight_diff_kg?: number | null
          declared_weight_kg?: number | null
          horse_id: number
          horse_number: number
          id?: never
          jockey_id?: number | null
          latest_place_odds_max?: number | null
          latest_place_odds_min?: number | null
          latest_win_odds?: number | null
          morning_line_popularity?: number | null
          race_id: number
          scratch_flag?: boolean
          sex_age?: string | null
          trainer_id?: number | null
          updated_at?: string
        }
        Update: {
          blinkers_flag?: boolean | null
          bracket_number?: number | null
          carried_weight?: number | null
          created_at?: string
          declared_weight_diff_kg?: number | null
          declared_weight_kg?: number | null
          horse_id?: number
          horse_number?: number
          id?: never
          jockey_id?: number | null
          latest_place_odds_max?: number | null
          latest_place_odds_min?: number | null
          latest_win_odds?: number | null
          morning_line_popularity?: number | null
          race_id?: number
          scratch_flag?: boolean
          sex_age?: string | null
          trainer_id?: number | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "race_entries_horse_id_fkey"
            columns: ["horse_id"]
            isOneToOne: false
            referencedRelation: "horses"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "race_entries_jockey_id_fkey"
            columns: ["jockey_id"]
            isOneToOne: false
            referencedRelation: "jockeys"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "race_entries_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: false
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "race_entries_trainer_id_fkey"
            columns: ["trainer_id"]
            isOneToOne: false
            referencedRelation: "trainers"
            referencedColumns: ["id"]
          },
        ]
      }
      race_results: {
        Row: {
          created_at: string
          going_final: string | null
          id: number
          lap_text: string | null
          pace_summary: string | null
          race_id: number
          result_fixed_at: string | null
          steward_notes: string | null
          updated_at: string
          weather_final: string | null
          winning_time: string | null
        }
        Insert: {
          created_at?: string
          going_final?: string | null
          id?: never
          lap_text?: string | null
          pace_summary?: string | null
          race_id: number
          result_fixed_at?: string | null
          steward_notes?: string | null
          updated_at?: string
          weather_final?: string | null
          winning_time?: string | null
        }
        Update: {
          created_at?: string
          going_final?: string | null
          id?: never
          lap_text?: string | null
          pace_summary?: string | null
          race_id?: number
          result_fixed_at?: string | null
          steward_notes?: string | null
          updated_at?: string
          weather_final?: string | null
          winning_time?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "race_results_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: true
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
        ]
      }
      racecourses: {
        Row: {
          created_at: string
          external_racecourse_code: string
          id: number
          is_active: boolean
          name: string
          region: string | null
          short_name: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          external_racecourse_code: string
          id?: never
          is_active?: boolean
          name: string
          region?: string | null
          short_name: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          external_racecourse_code?: string
          id?: never
          is_active?: boolean
          name?: string
          region?: string | null
          short_name?: string
          updated_at?: string
        }
        Relationships: []
      }
      races: {
        Row: {
          class_name: string | null
          created_at: string
          data_source: string
          distance_m: number
          external_race_code: string
          field_size: number | null
          going: string | null
          grade: string | null
          id: number
          race_date: string
          race_name: string | null
          race_number: number
          racecourse_id: number
          scheduled_start_at: string | null
          status: string
          track_type: string
          turn_type: string | null
          updated_at: string
          weather: string | null
        }
        Insert: {
          class_name?: string | null
          created_at?: string
          data_source: string
          distance_m: number
          external_race_code: string
          field_size?: number | null
          going?: string | null
          grade?: string | null
          id?: never
          race_date: string
          race_name?: string | null
          race_number: number
          racecourse_id: number
          scheduled_start_at?: string | null
          status?: string
          track_type: string
          turn_type?: string | null
          updated_at?: string
          weather?: string | null
        }
        Update: {
          class_name?: string | null
          created_at?: string
          data_source?: string
          distance_m?: number
          external_race_code?: string
          field_size?: number | null
          going?: string | null
          grade?: string | null
          id?: never
          race_date?: string
          race_name?: string | null
          race_number?: number
          racecourse_id?: number
          scheduled_start_at?: string | null
          status?: string
          track_type?: string
          turn_type?: string | null
          updated_at?: string
          weather?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "races_racecourse_id_fkey"
            columns: ["racecourse_id"]
            isOneToOne: false
            referencedRelation: "racecourses"
            referencedColumns: ["id"]
          },
        ]
      }
      recommendation_audits: {
        Row: {
          created_at: string
          feature_set_id: number
          id: number
          model_version_id: number
          payload_json: Json
          prediction_generated_at: string
          published_at: string | null
          race_entry_id: number | null
          race_id: number
        }
        Insert: {
          created_at?: string
          feature_set_id: number
          id?: never
          model_version_id: number
          payload_json: Json
          prediction_generated_at: string
          published_at?: string | null
          race_entry_id?: number | null
          race_id: number
        }
        Update: {
          created_at?: string
          feature_set_id?: number
          id?: never
          model_version_id?: number
          payload_json?: Json
          prediction_generated_at?: string
          published_at?: string | null
          race_entry_id?: number | null
          race_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "recommendation_audits_feature_set_id_fkey"
            columns: ["feature_set_id"]
            isOneToOne: false
            referencedRelation: "feature_sets"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "recommendation_audits_model_version_id_fkey"
            columns: ["model_version_id"]
            isOneToOne: false
            referencedRelation: "model_versions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "recommendation_audits_race_entry_id_fkey"
            columns: ["race_entry_id"]
            isOneToOne: false
            referencedRelation: "race_entries"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "recommendation_audits_race_id_fkey"
            columns: ["race_id"]
            isOneToOne: false
            referencedRelation: "races"
            referencedColumns: ["id"]
          },
        ]
      }
      saved_filters: {
        Row: {
          created_at: string
          deleted_at: string | null
          filter_json: Json
          filter_name: string
          filter_type: string
          id: number
          is_default: boolean
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          deleted_at?: string | null
          filter_json: Json
          filter_name: string
          filter_type: string
          id?: never
          is_default?: boolean
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          deleted_at?: string | null
          filter_json?: Json
          filter_name?: string
          filter_type?: string
          id?: never
          is_default?: boolean
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "saved_filters_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "user_profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      system_logs: {
        Row: {
          context_json: Json | null
          created_at: string
          event_type: string
          id: number
          job_run_id: number | null
          level: string
          message: string
          occurred_at: string
        }
        Insert: {
          context_json?: Json | null
          created_at?: string
          event_type: string
          id?: never
          job_run_id?: number | null
          level: string
          message: string
          occurred_at?: string
        }
        Update: {
          context_json?: Json | null
          created_at?: string
          event_type?: string
          id?: never
          job_run_id?: number | null
          level?: string
          message?: string
          occurred_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "system_logs_job_run_id_fkey"
            columns: ["job_run_id"]
            isOneToOne: false
            referencedRelation: "job_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      trainers: {
        Row: {
          affiliation: string | null
          created_at: string
          external_trainer_code: string
          id: number
          name: string
          updated_at: string
        }
        Insert: {
          affiliation?: string | null
          created_at?: string
          external_trainer_code: string
          id?: never
          name: string
          updated_at?: string
        }
        Update: {
          affiliation?: string | null
          created_at?: string
          external_trainer_code?: string
          id?: never
          name?: string
          updated_at?: string
        }
        Relationships: []
      }
      user_profiles: {
        Row: {
          created_at: string
          deleted_at: string | null
          display_name: string | null
          id: string
          last_login_at: string | null
          role: string
          status: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          deleted_at?: string | null
          display_name?: string | null
          id: string
          last_login_at?: string | null
          role?: string
          status?: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          deleted_at?: string | null
          display_name?: string | null
          id?: string
          last_login_at?: string | null
          role?: string
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      user_subscriptions: {
        Row: {
          created_at: string
          ended_at: string | null
          id: number
          plan_code: string
          provider_subscription_id: string | null
          started_at: string
          status: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          ended_at?: string | null
          id?: never
          plan_code?: string
          provider_subscription_id?: string | null
          started_at?: string
          status?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          ended_at?: string | null
          id?: never
          plan_code?: string
          provider_subscription_id?: string | null
          started_at?: string
          status?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_subscriptions_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "user_profiles"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      is_admin: { Args: never; Returns: boolean }
      is_approved: { Args: never; Returns: boolean }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const

