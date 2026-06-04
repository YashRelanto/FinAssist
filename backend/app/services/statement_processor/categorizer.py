from typing import Dict, Optional, Tuple, List, Any
from app.utils.supabase_client import supabase

class Categorizer:
    """
    Deterministic V1 Transaction Categorization.
    Maps standardized merchants to core main categories, defaulting unknown merchants to 'Others'.
    Resolves category IDs dynamically from the existing database 'categories' table.
    """

    # V1 Static Mapping from standard normalized merchants to main categories
    _STATIC_MERCHANT_MAP = {
        "AMAZON": "Shopping",
        "FLIPKART": "Shopping",
        "MYNTRA": "Shopping",
        "NYKAA": "Shopping",
        "MEESHO": "Shopping",
        "SNAPDEAL": "Shopping",
        
        "SWIGGY": "Food & Drinks",
        "ZOMATO": "Food & Drinks",
        "DOMINOS": "Food & Drinks",
        "PIZZA": "Food & Drinks",
        "BLINKIT":"Food & Drinks",
        "ZEPTO":"Food & Drinks",
        "INSTAMART":"Food & Drinks",     
           
        "UBER": "Transportation",
        "OLA": "Transportation",
        "RAPIDO": "Transportation",
        "METRO": "Transportation",
        "IRCTC": "Transportation",
        
        "NETFLIX": "Life & Entertainment",
        "SPOTIFY": "Life & Entertainment",
        "HOTSTAR": "Life & Entertainment",
        "PRIME": "Life & Entertainment",
        
        "AIRTEL": "Communication/PC",
        "JIO": "Communication/PC",
        "VODAFONE": "Communication/PC",
        
        "HDFC HOME LOAN": "Housing",
        "RENT": "Housing",
        "ELECTRICITY": "Housing",
        
        "SIP": "Investments",
        "MUTUAL FUND": "Investments",
        "GROWW": "Investments",
        "ZERODHA": "Investments",
        
        "SALARY": "Income",
        "WAGES": "Income",
        
        "ATM": "Others",
        "CASH": "Others",
    }

    @classmethod
    def _get_category_id_by_name(cls, main_category_name: str, db_categories: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """
        Dynamically queries categories in Supabase to retrieve the matching category UUID.
        Handles variations like 'Financial Expenses' vs 'Financial Expense'.
        """
        try:
            categories_list = db_categories
            if categories_list is None:
                db_res = supabase.table("categories").select("category_id, main_category").execute()
                categories_list = db_res.data if db_res else []

            # 1. Try exact match
            for row in categories_list:
                if row["main_category"].lower() == main_category_name.lower():
                    return row["category_id"]

            # 2. Try flexible ilike contains
            if categories_list:
                cleaned_name = main_category_name.lower().replace(" ", "").replace("&", "and").replace("/", "")
                for row in categories_list:
                    db_name = row["main_category"].lower().replace(" ", "").replace("&", "and").replace("/", "")
                    if cleaned_name in db_name or db_name in cleaned_name:
                        return row["category_id"]
        except Exception as e:
            print(f"Supabase categories query failed: {e}")
        return None

    @classmethod
    def resolve_category(
        cls,
        normalized_merchant: str,
        user_id: str,
        user_overrides: Optional[List[Dict[str, Any]]] = None,
        master_merchants: Optional[List[Dict[str, Any]]] = None,
        db_categories: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, str]:
        """
        Maps a normalized merchant to a category_id and category_name using V1 Hierarchical Strategy.
        Returns: Tuple[category_id_uuid_string, category_name_string]
        """
        category_name = "Others" # V1 default fallback

        # ── Step 1: Check User Personal Overrides ──
        try:
            overrides_list = user_overrides
            if overrides_list is None:
                override = supabase.table("user_category_overrides")\
                    .select("override_category_id, categories(main_category), merchant_name")\
                    .eq("user_id", user_id)\
                    .eq("merchant_name", normalized_merchant.upper())\
                    .execute()
                overrides_list = override.data if override else []

            for row in overrides_list:
                row_merchant = row.get("merchant_name")
                if row_merchant is None or row_merchant.upper() == normalized_merchant.upper():
                    cat_id = row.get("override_category_id")
                    cat_data = row.get("categories")
                    cat_name = cat_data.get("main_category") if cat_data else "Others"
                    if cat_id:
                        return cat_id, cat_name
        except Exception as e:
            print(f"Supabase override checks failed: {e}")

        # ── Step 2: Check Merchant master mapping ──
        try:
            merchants_list = master_merchants
            if merchants_list is None:
                master_match = supabase.table("merchant_master")\
                    .select("merchant_name, category")\
                    .eq("merchant_name", normalized_merchant.upper())\
                    .execute()
                merchants_list = master_match.data if master_match else []

            for row in merchants_list:
                if row["merchant_name"].upper() == normalized_merchant.upper():
                    category_name = row["category"]
                    break
        except Exception as e:
            print(f"Supabase merchant_master check failed: {e}")

        # ── Step 3: Check V1 static mappings if category is still unmapped ──
        if category_name == "Others":
            normalized_upper = normalized_merchant.upper()
            
            # Simple substring checking
            for merchant_key, mapped_cat in cls._STATIC_MERCHANT_MAP.items():
                if merchant_key in normalized_upper:
                    category_name = mapped_cat
                    break

        # ── Step 4: Database UUID Lookup ──
        category_id = cls._get_category_id_by_name(category_name, db_categories=db_categories)
        
        # Absolute fallback if category_id could not be resolved from DB:
        if not category_id:
            category_id = cls._get_category_id_by_name("Others", db_categories=db_categories)
            category_name = "Others"

        return category_id, category_name
