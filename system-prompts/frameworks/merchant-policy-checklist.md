# Merchant Center Misrepresentation - Alignment Checklist

Reference for `/55-merchant-policy-check`. Merged from Google's own policy pages and practitioner checklists, deduplicated. **[auto]** = checked by `scripts/merchant_policy_check.py`; **[read]** = Claude checks from the saved page texts; **[manual]** = needs a person (Merchant Center UI, browser, or the client). Every [auto] content check is a keyword heuristic: a WARN means "read it", never a verdict.

Sources: Google Misrepresentation policy (support.google.com/merchants/answer/6150127), Merchant Center website requirements (answer/6363310), Building trust with your customers (answer/13693865), third-party Merchant Center approval checklists, misrepresentation-recovery walkthroughs and a 2026 GMC compliance guide (all rewritten in our own words).

## How Google enforces it
- **Egregious, suspension without warning:** unacceptable business practices (false identity/contact info, hidden business location, impersonation, fake affiliation), coordinated deception, dishonest pricing/transaction conditions (hidden fees, delivery delays in small print, undisclosed restocking/return fees).
- **7-day warning first:** unavailable offers (listing items you can't fulfil, a catalogue that is mostly sold out, fake local inventory), manipulated media, unreliable claims.
- It is rarely one item. Small gaps add up (missing hours + generic About + shipping page that doesn't match checkout), so go through every section, not only the obvious ones.
- Reviews take ~7 business days. Reviewers do a quick scan: they copy the MC phone/address and look for it on the site, open the footer, open a product, try checkout. A first rejection after fixes is common - re-check everything, then resubmit.

## 1. Business identity (consistency is the whole game)
- [auto] MC business address, phone, email all visible on the website (footer + contact page).
- [auto] Footer of the homepage shows business name, address, phone, email as real text (a name inside the logo image doesn't count).
- [auto] Business contact details on every policy page (shipping, returns, privacy, terms) - a sitewide footer that holds them is enough.
- [auto] Only one set of contact details across pages - extra phones/emails/addresses must be clearly labelled (shop vs office) and all reachable.
- [auto] Policy pages name only this store - no other company's website, email, address or legal details (copied templates = false identity).
- [auto] Branded email on the store domain, not gmail/ukr.net etc. (trust signal, not a hard rule) - in MC and on the site.
- [auto] MC business name matches the site brand and domain; MC website URL = the claimed domain; website claimed.
- [auto] MC customer-service URL filled in and pointing at the contact page, not the homepage.
- [read] Legal entity (company name, registration number/ЄДРПОУ/NIP, registered address) stated somewhere (terms/contact) and consistent with MC.
- [manual] Google Business Profile, Google Ads account, social profiles and directory listings show the same name/address/phone.
- [manual] Address is a real place of business (residential is fine; PO box / virtual office is not). Phone is answered with the business name or has a voicemail.
- [manual] Logo text matches the full domain/brand name (e.g. "Brian New York", not just "Brian").
- [manual] Dropshipping / third-party fulfilment: say where products ship from and real delivery times; never imply local stock you don't have. A warehouse/dispatch address helps.

## 2. Required pages, linked in the footer of every page and at checkout
- [auto] Contact page - form alone is not enough; address, email, phone on it. Business hours [auto] and an expected response time ("we reply within 24 hours") [auto] recommended.
- [auto] About page - real story/mission, own photos of team/workspace/production (not stock); [auto] no generic AI filler phrases; [read] reads like the owner wrote it (when it started, where, why) and has no ChatGPT residue.
- [auto] Privacy policy - standalone page, required whenever any customer data is collected. [auto] Content: what data, why, who it's shared with, how long it's kept, how to delete/opt out, ads/analytics use, the applicable law (UA: law on personal data protection; EU: GDPR/RODO/DSGVO), a controller contact. Don't add CCPA for non-US stores just because a checklist says so.
- [auto] Terms / public offer - store rules, dispute handling, liability. [auto] Also: acceptance by using/ordering, intellectual property, termination, how changes are announced, seller contact. [read] Product categories mentioned match what the store sells (a foreign category = copied template).
- [auto] No blanket "not responsible for lost/damaged/stolen parcels" disclaimer - until delivery the risk is the seller's; describe how lost/damaged parcels are handled instead.
- [auto] Shipping policy - carriers, costs (and free-shipping threshold), destinations, handling time + transit time as explicit numbers, cut-off time. [auto] Also: business days stated, where you do NOT ship, how to track the order, customs/import taxes if shipping abroad.
- [auto] Returns/refund policy - window counted from delivery, conditions, at least two ways to start a return (e.g. email + phone, plus what to include), who pays return shipping, refund timing, refund method (original payment / store credit), restocking fee stated either way. Required even if you don't accept returns - then [auto] say "no returns" plainly, and [auto] also on product pages.
- [auto] Policies cover the problem cases: damaged item, wrong item, never arrived/lost, incomplete order. [auto] Order cancellation terms stated.
- [auto] Shipping and returns on separate pages (one combined page is a common finding).
- [auto] Policy links present on every key page (sitewide footer), on product pages, and on the checkout page.
- [auto] FAQ page and "Track your order" page linked (recommended). [auto] Payment methods shown in the footer (logos) and explained on a policy page.
- [auto] Header menu has About + Contact and names what you sell - no vague "All products" / "Collection".
- [auto] No placeholder/template text (lorem ipsum, `{$SITE_URL}`, "coming soon", sample pages).
- [read] Policy language = the target market's language.

## 3. Merchant Center settings = website, word for word
- [auto] Shipping times in MC (handling + transit) = shipping page.
- [auto] Shipping cost in MC = shipping page = what checkout actually charges. If the site says "carrier tariff, paid by the buyer", MC must use carrier/table rates, not an invented flat fee.
- [auto] Return policy in MC (type, days, fees) = returns page; MC return-policy URL live and on the store domain.
- [auto] Free-shipping threshold claimed on the homepage = threshold on the shipping page.
- [read] FAQ answers, homepage FAQ, announcement bar and product-page shipping notes use the same numbers as the policies (FAQ "3-4 days" vs policy "3-5 days" is a mismatch). Destinations claimed ("worldwide") = destinations checkout accepts.
- [manual] MC Settings -> Business info, Shipping and returns, Tax, open in the UI once to confirm nothing the API doesn't show (e.g. a second shipping service). Any active MC promotion actually works at checkout.

## 4. Product pages and feed
- [auto] Active feed with products (the Request review button needs it); disapproved items fixed first (details: `/55-merchant-review`).
- [auto] Feed links on the claimed domain, return 200, no redirect to the homepage.
- [auto] Feed price = price on the page (including the selected variant on variable products), availability = page, condition = page.
- [auto] Feed title and image match what the landing page shows.
- [auto] Feed titles without promo text or emojis ("free shipping", "sale", "-20%").
- [auto] Feed descriptions not thin (25+ words), no ChatGPT copy-paste markup in descriptions or on site pages.
- [auto] No discounts deeper than 50% (feed sale prices and strike-through prices on product pages); sale prices carry an end date.
- [auto] Feed size close to the site catalogue (sitemap); most of the feed in stock; homepage doesn't showcase sold-out products. Sold out with no restock date -> hide it; with a date -> pre-order with the date.
- [auto] Product pages: shipping/returns linked, a delivery note on the page itself (near Add to cart, not only in the footer), a reviews section (an empty verified-buyer widget is fine).
- [auto] No fake urgency (any countdown timer - even real ones are reported to trigger reviews - false "only N left", fake "X people viewing").
- [auto] No unverified security/trust badges (McAfee, Norton, "guaranteed safe checkout") the store isn't certified for.
- [read] Descriptions unique and accurate (not copied); no medical/miracle/false material claims ("100% leather" on polyester); claims about results/durability backed or disclaimed.
- [read] Pre-order/backorder stated on the product page and in the feed (`availability`, `availability_date`).
- [manual] Product images are your own, not the supplier's/AliExpress images found on many other sites (Google Lens check).
- [manual] Homepage shows the real range (categories/bestsellers), looks like a focused store in one niche (not gadgets + lamps + clothing), not one product with several "Shop now" buttons; collections contain the right products; on product pages "Add to cart" is the main action.
- [manual] Made-to-order / custom products: `identifier_exists = no` when there is no GTIN, the most specific `google_product_category`, production time inside MC handling time (feed data quality - `/55-merchant-review` territory).

## 5. Technical
- [auto] HTTPS everywhere, checkout opens with a product in the cart, no redirect loops.
- [manual] No broken links (run a whole-site dead-link checker), no pop-ups blocking content on first load (age gates are fine for alcohol), mobile works.

## 6. Requesting the review
1. Fix everything above first - one review with half the fixes burns a cycle (reviews take ~7 business days).
2. Merchant Center -> Needs attention / Account issues -> Request review.
3. Optionally contact Google Merchant Center support (chat/email via the Help menu) first and ask for a manual review/escalation. Template:
   > Hi, we've corrected all misrepresentation issues on [domain]: [list concrete fixes - e.g. replaced the copied public offer with our own legal details, added a privacy policy, aligned shipping costs in Merchant Center with checkout]. Business information on the site now matches Merchant Center exactly. Could you please escalate this for a manual review?
4. If rejected, re-run the check, re-read sections 1-4, resubmit.

## 7. Prevention
- Monthly: re-run `/55-merchant-policy-check`, review policies, check feed accuracy and the price match ad = page = checkout after any price change, remove plugins/apps that add urgency, fake reviews or badges.
- Weekly: Merchant Center "Needs attention". Also watch Google Search Console and Google's policy change log.

## Deliberately not in this checklist
Proxies, several Merchant Center accounts per company, deleting accounts "without traces", "warming up" accounts and bought reviews (all suggested in practitioner material) - these evade enforcement rather than comply, and get accounts permanently banned. Also not used: "Google scans for the words GDPR/CCPA", white-background-only images and MC brand colours/logos as misrepresentation factors - no Google source, they'd create false findings.
